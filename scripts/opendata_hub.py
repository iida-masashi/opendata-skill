import importlib
import logging
import re
import sys
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType
from typing import Any

import polars as pl

from .cache_manager import CacheManager

logger = logging.getLogger(__name__)

# フェッチャーは `from api_utils import ...` / `from fred_fetcher import ...` のように
# scripts/ 直下をトップレベルとして import する。Hub をライブラリとして使う場合でも
# 解決できるよう、scripts/ を import パスに載せる。
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# フェッチャーが送出するのはトップレベル `api_utils` のクラス。`scripts.api_utils` から import すると
# 別モジュール扱いで別クラスになり except で捕まらないため、利用者向けにここから公開する。
from api_utils import MissingApiKeyError  # noqa: E402

__all__ = ["MissingApiKeyError", "OpenDataHub"]


class OpenDataHub:
    """
    opendata-skill の各種フェッチャーを統合管理するハブ。
    個別スクリプトを意識せずに、単一インターフェースからデータ取得・キャッシュ・正規化を行う。
    """

    def __init__(self, cache_dir: str = ".cache") -> None:
        self.scripts_dir: Path = _SCRIPTS_DIR
        self.fetchers: dict[str, Path] = self._discover_fetchers()
        self.cache = CacheManager(cache_dir=cache_dir)
        # 直近の get_many で失敗したラベル → 例外（失敗と「データ0件」を区別するため）
        self.last_errors: dict[str, Exception] = {}

    def _discover_fetchers(self) -> dict[str, Path]:
        """scripts ディレクトリ内のフェッチャーを自動検出する"""
        fetchers: dict[str, Path] = {}
        for file in self.scripts_dir.glob("*_fetcher.py"):
            name = file.name.replace("_fetcher.py", "")
            fetchers[name] = file
        return fetchers

    def _load_module(self, name: str) -> ModuleType:
        """フェッチャーモジュールを import する（sys.modules にキャッシュされ、2回目以降は再実行しない）。

        再実行するとモジュール状態（rate_limited の実行枠など）が毎回リセットされるため、
        通常の import でロードする。
        """
        if name not in self.fetchers:
            raise ValueError(
                f"Unknown fetcher: {name}. Available: {list(self.fetchers.keys())}"
            )
        return importlib.import_module(self.fetchers[name].stem)

    def get_many(
        self, specs: list[dict[str, Any]], max_workers: int = 8
    ) -> dict[str, pl.DataFrame]:
        """複数ソースを並列に取得する（I/Oバウンドなのでスレッドで十分）。

        specs: [{"label": str, "method": "get_xxx", "kwargs": {...}}, ...]
        戻り値: {label: DataFrame}。個々の失敗は隔離し、その label は空DFになる
        （1ソースのAPI障害が全体を巻き込まないようにする）。
        失敗したラベルと例外は self.last_errors に入る（空DFが「0件」か「失敗」かはここで区別する）。
        """
        def _run(spec: dict[str, Any]) -> tuple[str, pl.DataFrame, Exception | None]:
            label = spec["label"]
            try:
                fn = getattr(self, spec["method"])
                df = fn(**spec.get("kwargs", {}))
                return label, df if isinstance(df, pl.DataFrame) else pl.DataFrame(), None
            except Exception as e:  # noqa: BLE001 - 失敗を隔離して全体を守る
                logger.error("[get_many] '%s' (%s) failed: %s", label, spec.get("method"), e)
                return label, pl.DataFrame(), e

        results: dict[str, pl.DataFrame] = {}
        errors: dict[str, Exception] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            for label, df, err in ex.map(_run, specs):
                results[label] = df
                if err is not None:
                    errors[label] = err
        self.last_errors = errors
        return results

    def get_weather(self, lat: float, lon: float, **kwargs: Any) -> pl.DataFrame:
        """気象データを取得する (Open-Meteo)"""
        return self._cached_fetch(
            "meteo", "fetch_open_meteo", "weather",
            {"lat": lat, "lon": lon, **kwargs}, 24,
            {"latitude": lat, "longitude": lon, **kwargs},
        )

    def get_weather_ensemble(
        self,
        lat: float,
        lon: float,
        variables: str | Sequence[str] | None = None,
        model: str = "icon_seamless",
        daily: bool = True,
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: Any,
    ) -> pl.DataFrame:
        """Open-Meteo アンサンブル気象予報（確率分布 P10/P50/P90・標準偏差）を取得する"""
        call = {
            "latitude": lat,
            "longitude": lon,
            "variables": list(variables) if isinstance(variables, (list, tuple)) else variables,
            "model": model,
            "daily": daily,
            "start_date": start_date,
            "end_date": end_date,
            **kwargs,
        }
        return self._cached_fetch(
            "meteo", "fetch_open_meteo_ensemble", "weather_ensemble",
            call, 6, call,
        )

    def get_economic(
        self, indicators: list[str], countries: str = "all", **kwargs: Any
    ) -> pl.DataFrame:
        """世界銀行から経済指標を取得する"""
        return self._cached_fetch(
            "worldbank", "fetch_worldbank_data", "worldbank",
            {"indicators": sorted(indicators), "countries": countries, **kwargs}, 168,  # 1 week
            {"indicators": indicators, "countries": countries, **kwargs},
        )

    def get_trends(
        self, keywords: list[str], geo: str = "JP", **kwargs: Any
    ) -> pl.DataFrame:
        """Googleトレンドを取得する"""
        return self._cached_fetch(
            "trends", "fetch_google_trends", "trends",
            {"keywords": sorted(keywords), "geo": geo, **kwargs}, 24,
            {"keywords": keywords, "geo": geo, **kwargs},
        )

    def get_wikipedia_views(
        self,
        articles: str | Sequence[str],
        lang: str = "ja",
        granularity: str = "daily",
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: Any,
    ) -> pl.DataFrame:
        """Wikipedia 記事の日次/月次ページビュー数（消費者関心の先行指標）を取得する (APIキー不要)"""
        art_param = list(articles) if isinstance(articles, (list, tuple)) else articles
        call = {
            "articles": art_param,
            "lang": lang,
            "granularity": granularity,
            "start_date": start_date,
            "end_date": end_date,
            **kwargs,
        }
        return self._cached_fetch(
            "wikipedia", "fetch_wikipedia_pageviews", "wikipedia",
            call, 24, call,
        )

    def get_freight(
        self,
        tickers: str = "BDRY",
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: Any,
    ) -> pl.DataFrame:
        """物流・海運コスト指標を取得する"""
        return self._cached_fetch(
            "freight", "fetch_freight_data", "freight",
            {"tickers": tickers, "start": start_date, "end": end_date, **kwargs}, 24,
            {"tickers": tickers, "start_date": start_date, "end_date": end_date, **kwargs},
        )

    def get_fred(
        self,
        series_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: Any,
    ) -> pl.DataFrame:
        """FREDからマクロ経済指標を取得する"""
        return self._cached_fetch(
            "fred", "fetch_fred_data", "fred",
            {"id": series_id, "start": start_date, "end": end_date, **kwargs}, 168,
            {"series_id": series_id, "start_date": start_date, "end_date": end_date, **kwargs},
        )

    def get_yahoo(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: Any,
    ) -> pl.DataFrame:
        """Yahoo Financeから市場データを取得する"""
        return self._cached_fetch(
            "yahoo", "fetch_yahoo_finance", "yahoo",
            {"symbol": symbol, "start": start_date, "end": end_date, **kwargs}, 12,  # Market data changes often
            {"tickers": symbol, "start_date": start_date, "end_date": end_date, **kwargs},
        )

    def get_oecd(
        self,
        dataset: str,
        countries: str = "all",
        start_year: int | None = None,
        end_year: int | None = None,
        **kwargs: Any,
    ) -> pl.DataFrame:
        """OECDから詳細な経済統計（QNA/SNA/MEI等）を取得する"""
        return self._cached_fetch(
            "oecd", "fetch_oecd_data", "oecd",
            {"dataset": dataset, "countries": countries, "start": start_year, "end": end_year, **kwargs},
            720,  # 30 days
            {"dataset_code": dataset, "countries": countries,
             "start_year": start_year, "end_year": end_year, **kwargs},
        )

    def get_estat(
        self, stats_data_id: str, app_id: str | None = None, **kwargs: Any
    ) -> pl.DataFrame:
        """e-Statから日本の公的統計を取得する"""
        params = {"id": stats_data_id, **kwargs}
        cached = self.cache.get("estat", params)
        if cached is not None:
            return cached

        from api_utils import require_api_key

        app_id = app_id or require_api_key("ESTAT_API_KEY", "e-Stat", "https://www.e-stat.go.jp/api/")
        return self._cached_fetch(
            "estat", "fetch_estat_data", "estat", params, 720,
            {"app_id": app_id, "stats_data_id": stats_data_id, **kwargs},
        )

    INDUSTRY_COMMODITY_MAP = {
        "食品": ["ZC=F", "ZS=F", "KE=F", "USDJPY=X"],
        "繊維": ["CT=F", "USDJPY=X"],
        "パルプ・紙": ["LBS=F", "USDJPY=X"],
        "化学": ["CL=F", "NG=F", "USDJPY=X"],
        "医薬品": ["EURJPY=X", "USDJPY=X"],
        "石油・石炭製品": ["CL=F", "HO=F", "RB=F"],
        "ゴム製品": ["CL=F", "USDJPY=X"],
        "ガラス・土石製品": ["NG=F", "USDJPY=X"],
        "鉄鋼": ["SLX", "CL=F", "USDJPY=X"],
        "非鉄金属": ["HG=F", "ALI=F", "LIT", "USDJPY=X"],
        "金属製品": ["HG=F", "SLX", "USDJPY=X"],
        "機械": ["HG=F", "SLX", "USDJPY=X"],
        "電気機器": ["HG=F", "LIT", "GC=F", "USDJPY=X"],
        "輸送用機器": ["CL=F", "HG=F", "SLX", "USDJPY=X"],
        "精密機器": ["GC=F", "SI=F", "USDJPY=X"],
        "その他製品": ["CL=F", "USDJPY=X"],
        "建設": ["LBS=F", "SLX", "HG=F"],
        "消費財": ["CL=F", "USDJPY=X", "CT=F"],
    }

    def get_commodity_proxies(
        self, industry: str, start_date: str | None = None, end_date: str | None = None, **kwargs: Any
    ) -> pl.DataFrame:
        """指定された全18産業に関連するコモディティ価格や為替のプロキシ指標を取得する"""
        if industry not in self.INDUSTRY_COMMODITY_MAP:
            raise ValueError(f"Unknown industry: {industry}. Available: {list(self.INDUSTRY_COMMODITY_MAP.keys())}")

        tickers = " ".join(self.INDUSTRY_COMMODITY_MAP[industry])
        return self.get_yahoo(symbol=tickers, start_date=start_date, end_date=end_date, **kwargs)

    def get_global_macro(
        self,
        region: str,
        indicators: list[str] | None = None,
        start_year: int | None = None,
        end_year: int | None = None,
        **kwargs: Any,
    ) -> pl.DataFrame:
        """CNやEUなどのグローバルマクロ指標をプリセットで取得する"""
        region_map = {
            "CN": "CHN",
            "EU": "EUU",
            "US": "USA",
            "JP": "JPN",
            "EA": "EMU",  # Euro Area
        }
        code = region_map.get(region.upper(), region)
        inds = indicators or ["gdp", "inflation", "unemployment"]

        return self.get_economic(indicators=inds, countries=code, start_year=start_year, end_year=end_year, **kwargs)

    def get_china_macro(self, start_year: int | None = None, end_year: int | None = None, **kwargs: Any) -> pl.DataFrame:
        """中国 (NBS相当) の主要マクロ指標をワンクリックで取得するプリセット"""
        return self.get_global_macro(
            region="CHN",
            indicators=["gdp_growth", "inflation", "unemployment", "gni"],
            start_year=start_year,
            end_year=end_year,
            **kwargs,
        )

    def get_europe_macro(self, start_year: int | None = None, end_year: int | None = None, **kwargs: Any) -> pl.DataFrame:
        """欧州 (Eurostat相当) の主要マクロ指標をワンクリックで取得するプリセット"""
        return self.get_global_macro(
            region="EUU,EMU",
            indicators=["gdp_growth", "inflation", "unemployment", "gdp"],
            start_year=start_year,
            end_year=end_year,
            **kwargs,
        )

    def get_us_macro(self, start_year: int | None = None, end_year: int | None = None, **kwargs: Any) -> pl.DataFrame:
        """米国 (BEA/BLS相当) の主要マクロ指標をワンクリックで取得するプリセット"""
        return self.get_global_macro(
            region="USA",
            indicators=["gdp_growth", "inflation", "unemployment", "gdp"],
            start_year=start_year,
            end_year=end_year,
            **kwargs,
        )

    # ========================================================================
    # SCM/需要予測向け先行指標・リスク・補完フェッチャー
    # ========================================================================

    def _cached_fetch(
        self,
        module_name: str,
        fetcher_name: str,
        cache_key: str,
        cache_params: dict[str, Any],
        ttl_hours: int,
        call_kwargs: dict[str, Any],
    ) -> pl.DataFrame:
        """キャッシュ確認 → フェッチ → キャッシュ保存の共通処理"""
        cached = self.cache.get(cache_key, cache_params)
        if cached is not None:
            return cached
        df = self._fetch_to_df(module_name, fetcher_name, call_kwargs)
        if not self._is_degenerate(df):
            self.cache.set(cache_key, cache_params, df, ttl_hours=ttl_hours)
        return df

    def get_pmi(self, series: str = "us_new_orders", **kwargs: Any) -> pl.DataFrame:
        """PMI・製造業先行指標 (FRED経由: 新規受注/OECD CLI/政策不確実性等)"""
        return self._cached_fetch(
            "pmi", "fetch_pmi_data", "pmi",
            {"series": series, **kwargs}, 168,
            {"series": series, **kwargs},
        )

    def get_comtrade(
        self, reporter: str = "JP", partner: str = "ALL", hs_code: str = "TOTAL",
        flow: str = "M", period: str | None = None, **kwargs: Any,
    ) -> pl.DataFrame:
        """UN Comtrade グローバル貿易フロー (HSコード粒度)"""
        call = {"reporter": reporter, "partner": partner, "hs_code": hs_code,
                "flow": flow, "period": period, **kwargs}
        cache_p = {"reporter": reporter, "partner": partner, "hs": hs_code,
                   "flow": flow, "period": period, **kwargs}
        return self._cached_fetch(
            "comtrade", "fetch_comtrade_data", "comtrade", cache_p, 720,
            call,
        )

    def get_eia(self, series: str = "crude_stocks", **kwargs: Any) -> pl.DataFrame:
        """EIA 米エネルギー需給 (石油・ガス在庫、精製稼働率)"""
        return self._cached_fetch(
            "eia", "fetch_eia_data", "eia",
            {"series": series, **kwargs}, 24,
            {"series": series, **kwargs},
        )

    def get_gdelt(self, query: str = "supply chain disruption", theme: str | None = None, **kwargs: Any) -> pl.DataFrame:
        """GDELT 地政学・SC断絶イベントデータ (APIキー不要)"""
        return self._cached_fetch(
            "gdelt", "fetch_gdelt_data", "gdelt",
            {"query": query, "theme": theme, **kwargs}, 6,
            {"query": query, "theme": theme, **kwargs},
        )

    def get_ais(self, port: str = "shanghai", provider: str = "auto", **kwargs: Any) -> pl.DataFrame:
        """AIS / 港湾混雑データ (BDIの先行指標)"""
        return self._cached_fetch(
            "ais", "fetch_ais_data", "ais",
            {"port": port, "provider": provider, **kwargs}, 2,
            {"port": port, "provider": provider, **kwargs},
        )

    def get_agri(self, source: str = "faostat", commodity: str = "corn", **kwargs: Any) -> pl.DataFrame:
        """USDA / FAOSTAT 農業・食品データ"""
        return self._cached_fetch(
            "usda", "fetch_agri_data", "usda",
            {"source": source, "commodity": commodity, **kwargs}, 720,
            {"source": source, "commodity": commodity, **kwargs},
        )

    def get_semicon(self, series: str = "us_semi_shipments", **kwargs: Any) -> pl.DataFrame:
        """半導体業界指標 (出荷/在庫/B2B比)"""
        if series == "book_to_bill":
            return self._cached_fetch(
                "semicon", "compute_book_to_bill", "semicon",
                {"series": series, **kwargs}, 168,
                kwargs,
            )
        return self._cached_fetch(
            "semicon", "fetch_semicon_data", "semicon",
            {"series": series, **kwargs}, 168,
            {"series": series, **kwargs},
        )

    def get_entsoe(self, data_type: str = "load_actual", country: str = "DE", **kwargs: Any) -> pl.DataFrame:
        """ENTSO-E 欧州電力需給データ"""
        call = {"data_type": data_type, "country": country, **kwargs}
        return self._cached_fetch(
            "entsoe", "fetch_entsoe_data", "entsoe", call, 6,
            call,
        )

    def get_usgs_earthquakes(self, min_magnitude: float = 4.5, **kwargs: Any) -> pl.DataFrame:
        """USGS グローバル地震データ (海外拠点リスク)"""
        return self._cached_fetch(
            "usgs", "fetch_usgs_earthquakes", "usgs",
            {"min_mag": min_magnitude, **kwargs}, 1,
            {"min_magnitude": min_magnitude, **kwargs},
        )

    def get_firms(self, region: str = "us_west", source: str = "viirs_n", **kwargs: Any) -> pl.DataFrame:
        """NASA FIRMS 山火事リアルタイム衛星データ"""
        call = {"region": region, "source": source, **kwargs}
        return self._cached_fetch(
            "firms", "fetch_firms_data", "firms", call, 3,
            call,
        )

    def get_official_fx(self, source: str = "ecb", currency: str = "JPY", **kwargs: Any) -> pl.DataFrame:
        """ECB / Frankfurter-JPY 為替レート (公的参照)"""
        call = {"source": source, "currency": currency, **kwargs}
        return self._cached_fetch(
            "official_fx", "fetch_official_fx", "official_fx", call, 24,
            call,
        )

    def get_edinet_financials(
        self, edinet_code: str, period: str = "annual", years: int | None = None, **kwargs: Any
    ) -> pl.DataFrame:
        """EDINET DBから財務データを取得する (edinetdb利用)"""
        call = {"edinet_code": edinet_code, "period": period, "years": years, **kwargs}
        return self._cached_fetch(
            "edinet", "fetch_edinet_financials", "edinet_financials", call, 24,
            call,
        )

    def get_edinet_ratios(self, edinet_code: str, **kwargs: Any) -> pl.DataFrame:
        """EDINET DBから財務比率データを取得する (edinetdb利用)"""
        call = {"edinet_code": edinet_code, **kwargs}
        return self._cached_fetch(
            "edinet", "fetch_edinet_ratios", "edinet_ratios", call, 24,
            call,
        )

    # ========================================================================
    # 日本の先行指標・需要予測プリセット (日銀 / e-Stat 各種統計)
    # ========================================================================

    def get_boj(self, series: str = "tankan_large_mfg", db: str | None = None, **kwargs: Any) -> pl.DataFrame:
        """日銀 時系列統計（短観DI、企業物価指数CGPI、SPPI、マネーストック等）を取得する"""
        call = {"series": series, "db": db, **kwargs}
        return self._cached_fetch(
            "boj", "fetch_boj_data", "boj", call, 168,
            call,
        )

    def get_boj_tankan(self, series: str = "tankan_large_mfg", **kwargs: Any) -> pl.DataFrame:
        """日銀 短観の業況判断DIなどを取得する (BOJ時系列API・キー不要)"""
        call = {"series": series, **kwargs}
        return self._cached_fetch(
            "boj", "fetch_boj_data", "boj", call, 168,
            call,
        )

    def get_cgpi(self, series: str = "cgpi_all", **kwargs: Any) -> pl.DataFrame:
        """日銀 企業物価指数 (CGPI: 国内・輸出・輸入) / SPPI を取得する (APIキー不要)"""
        return self.get_boj(series=series, **kwargs)

    @staticmethod
    def _filter_estat_text(df: pl.DataFrame, query: str) -> pl.DataFrame:
        """DataFrame 内の文字列カラムに query を含む行のみを抽出するヘルパー"""
        if df.is_empty():
            return df
        str_cols = [c for c, dt in zip(df.columns, df.dtypes, strict=False) if dt == pl.String and c not in ("date", "value", "unit")]
        if not str_cols:
            return df
        cond = pl.lit(False)
        for c in str_cols:
            cond = cond | pl.col(c).str.contains(query, literal=True).fill_null(False)
        return df.filter(cond)

    def get_keiki_di(self, series: str | None = None, **kwargs: Any) -> pl.DataFrame:
        """内閣府 景気動向指数 (CI/DI、先行指数を含む) を e-Stat 経由で取得する。

        series に '先行指数' や '一致指数' を指定すると該当系列のみに絞り込む。
        """
        df = self.get_estat(stats_data_id="0003446461", **kwargs)
        if series:
            df = self._filter_estat_text(df, series)
        return df

    def get_inbound_visitors(self, country: str | None = None, **kwargs: Any) -> pl.DataFrame:
        """訪日外客数 (港別 入国外国人の国籍・地域、月次) を e-Stat 経由で取得する。

        country に '韓国' や '中国'、'総数' 等を指定すると該当国籍・地域のみに絞り込む。
        """
        df = self.get_estat(stats_data_id="0003449064", **kwargs)
        if country:
            df = self._filter_estat_text(df, country)
        return df

    def get_retail_sales(self, **kwargs: Any) -> pl.DataFrame:
        """経産省 商業動態統計（業態別・商品別小売販売額・月次）を e-Stat 経由で取得する"""
        return self.get_estat(stats_data_id="0003355268", **kwargs)

    def get_industrial_production(self, **kwargs: Any) -> pl.DataFrame:
        """経産省 鉱工業指数 IIP（生産・出荷・在庫指数・月次）を e-Stat 経由で取得する"""
        return self.get_estat(stats_data_id="0003335036", **kwargs)

    def get_housing_starts(self, **kwargs: Any) -> pl.DataFrame:
        """国交省 建築着工統計調査（新設住宅着工戸数・月次）を e-Stat 経由で取得する"""
        return self.get_estat(stats_data_id="0003103532", **kwargs)

    def get_economy_watchers(self, **kwargs: Any) -> pl.DataFrame:
        """内閣府 景気ウォッチャー調査（現状・先行き判断DI・月次）を e-Stat 経由で取得する"""
        return self.get_estat(stats_data_id="0003348423", **kwargs)

    def get_household_spending(self, **kwargs: Any) -> pl.DataFrame:
        """総務省 家計調査（二人以上の世帯・品目分類別支出・月次）を e-Stat 経由で取得する"""
        return self.get_estat(stats_data_id="0003343671", **kwargs)

    def get_monthly_wages(self, **kwargs: Any) -> pl.DataFrame:
        """厚労省 毎月勤労統計調査（現金給与総額・実質賃金指数・月次）を e-Stat 経由で取得する"""
        return self.get_estat(stats_data_id="0003318162", **kwargs)

    def get_population(self, **kwargs: Any) -> pl.DataFrame:
        """総務省 人口推計（各月1日現在人口）を e-Stat 経由で取得する"""
        return self.get_estat(stats_data_id="0003448237", **kwargs)

    def get_cpi(self, **kwargs: Any) -> pl.DataFrame:
        """総務省 2020年基準消費者物価指数（全国・月次）を e-Stat 経由で取得する"""
        return self.get_estat(stats_data_id="0003427113", **kwargs)

    def get_labor_force(self, **kwargs: Any) -> pl.DataFrame:
        """総務省 労働力調査（基本集計・全国月次）を e-Stat 経由で取得する"""
        return self.get_estat(stats_data_id="0003005798", **kwargs)

    # ========================================================================
    # 地理・環境・交通・SNS・その他フェッチャー統合メソッド
    # ========================================================================

    def get_air_quality(self, lat: float, lon: float, **kwargs: Any) -> pl.DataFrame:
        """大気質・花粉・PM2.5データを取得する (Open-Meteo Air Quality)"""
        call = {"latitude": lat, "longitude": lon, **kwargs}
        return self._cached_fetch("air_quality", "fetch_air_quality", "air_quality", call, 12, call)

    def get_river(self, lat: float, lon: float, **kwargs: Any) -> pl.DataFrame:
        """河川流量・洪水リスクデータを取得する (Open-Meteo GloFAS)"""
        call = {"latitude": lat, "longitude": lon, **kwargs}
        return self._cached_fetch("river", "fetch_river_discharge", "river", call, 12, call)

    def get_holiday(self, **kwargs: Any) -> pl.DataFrame:
        """内閣府 日本の国民の祝日データを取得する"""
        return self._cached_fetch("holiday", "fetch_japan_holidays", "holiday", kwargs, 720, kwargs)

    def get_events(self, year: int | None = None, country_code: str = "JP", **kwargs: Any) -> pl.DataFrame:
        """国別の祝日・カレンダーイベントフラグを取得する (Nager.Date API)"""
        call = {"year": year, "country_code": country_code, **kwargs}
        return self._cached_fetch("events", "fetch_events_data", "events", call, 720, call)

    def get_mlit(self, year: int, area: str, **kwargs: Any) -> pl.DataFrame:
        """国交省 不動産情報ライブラリから不動産取引価格・地価を取得する"""
        call = {"year": year, "area": area, **kwargs}
        return self._cached_fetch("mlit", "fetch_land_prices", "mlit", call, 720, call)

    def get_odpt(self, rdf_type: str, **kwargs: Any) -> pl.DataFrame:
        """ODPT 公共交通オープンデータから運行・時刻表データを取得する"""
        call = {"rdf_type": rdf_type, **kwargs}
        return self._cached_fetch("odpt", "fetch_odpt_data", "odpt", call, 6, call)

    def get_plateau(self, query: str, **kwargs: Any) -> pl.DataFrame:
        """3D都市モデル PLATEAU のデータセットを検索・取得する"""
        call = {"query": query, **kwargs}
        return self._cached_fetch("plateau", "fetch_plateau_model", "plateau", call, 720, call)

    def get_jshis(self, lat: float, lon: float, **kwargs: Any) -> pl.DataFrame:
        """J-SHIS 地震ハザードステーションから地点別地震リスクを取得する"""
        call = {"lat": lat, "lon": lon, **kwargs}
        return self._cached_fetch("jshis", "fetch_jshis_risk", "jshis", call, 720, call)

    def get_power(self, area: str = "tokyo", date: str | None = None, **kwargs: Any) -> pl.DataFrame:
        """電力需給実績データ (TEPCO でんき予報) を取得する"""
        call = {"area": area, "date": date, **kwargs}
        return self._cached_fetch("power", "fetch_power_usage", "power", call, 6, call)

    def get_gsi(self, query: str, **kwargs: Any) -> pl.DataFrame:
        """国土地理院ジオコーディングAPIから住所・地名の緯度経度を取得する"""
        call = {"query": query, **kwargs}
        return self._cached_fetch("gsi", "fetch_gsi_msearch", "gsi", call, 720, call)

    def get_zipcode(self, zipcode: str, **kwargs: Any) -> pl.DataFrame:
        """郵便番号から住所情報を取得する (zipcloud)"""
        call = {"zipcode": zipcode, **kwargs}
        return self._cached_fetch("zipcode", "fetch_zipcode", "zipcode", call, 720, call)

    def get_corp(self, target: str, mode: str = "name", **kwargs: Any) -> pl.DataFrame:
        """国税庁 法人番号公表サイトAPIから企業情報を取得する"""
        call = {"target": target, "mode": mode, **kwargs}
        return self._cached_fetch("corp", "fetch_corporate_info", "corp", call, 720, call)

    def get_ckan(
        self, query: str, base_url: str = "https://data.e-gov.go.jp/data", rows: int = 10, **kwargs: Any
    ) -> pl.DataFrame:
        """e-Gov データポータル等の CKAN カタログからCSVリソースを検索する"""
        call = {"base_url": base_url, "query": query, "rows": rows, **kwargs}
        return self._cached_fetch("ckan", "search_ckan", "ckan", call, 24, call)

    def get_youtube(self, video_id: str, max_results: int = 100, **kwargs: Any) -> pl.DataFrame:
        """YouTube Data API v3 から動画コメントを取得する"""
        call = {"video_id": video_id, "max_results": max_results, **kwargs}
        return self._cached_fetch("youtube", "fetch_youtube_comments", "youtube", call, 24, call)

    def get_x_grok(self, query: str, limit: int = 10, **kwargs: Any) -> pl.DataFrame:
        """xAI Grok API 経由で X (旧Twitter) のトレンド・センチメントを取得する"""
        call = {"query": query, "limit": limit, **kwargs}
        return self._cached_fetch("x_grok", "fetch_x_grok", "x_grok", call, 6, call)

    @staticmethod
    def _is_degenerate(df: pl.DataFrame) -> bool:
        """予測の外生変数として使えない退化したDFかを判定する。

        空、または全カラムが全行null のものは退化とみなす（キャッシュしない）。
        """
        if df.is_empty():
            return True
        return all(df[c].null_count() == df.height for c in df.columns)

    @staticmethod
    def _normalize_df(df: pl.DataFrame) -> pl.DataFrame:
        """カラム名を date / value へ標準化する（hub→下流の契約）。

        - WorldBank の横持ち (YR2020, YR2021, ...) は縦持ち (date, value) へ unpivot する。
        - OECD の TIME_PERIOD 等も date に正規化する。
        - 複数列が同じ正規化名に衝突する場合は最初の1列だけ採用し、rename の
          DuplicateError を防ぐ。冪等。
        """
        if df.is_empty():
            return df

        yr_cols = [c for c in df.columns if re.fullmatch(r"YR\d{4}", c)]
        if yr_cols and "date" not in df.columns and "value" not in df.columns:
            id_cols = [c for c in df.columns if c not in yr_cols]
            df = (
                df.unpivot(
                    on=yr_cols,
                    index=id_cols,
                    variable_name="date",
                    value_name="value",
                )
                .with_columns(
                    pl.col("date").str.strip_prefix("YR"),
                    pl.col("value").cast(pl.Float64, strict=False),
                )
            )
            return df

        mapping: dict[str, str] = {}
        used: set[str] = set()

        def _claim(col: str, target: str) -> None:
            if target not in used:
                mapping[col] = target
                used.add(target)

        for col in df.columns:
            c_low = col.lower()
            if c_low in ["date", "time", "時間", "time_period"]:
                _claim(col, "date")
            elif c_low in ["value", "close", "adj close", "値"]:
                _claim(col, "value")

        return df.rename(mapping) if mapping else df

    def _fetch_to_df(
        self, module_name: str, fetcher_name: str, call_kwargs: dict[str, Any]
    ) -> pl.DataFrame:
        """フェッチャーを呼び、戻り値の DataFrame を正規化して返す。

        フェッチャーは DataFrame を返す契約（CSV は書かせない）。None 等が返ったら
        「データ無し」と区別できなくなるので TypeError にする。
        """
        m = self._load_module(module_name)
        fetcher = getattr(m, fetcher_name)
        result = fetcher(**call_kwargs)
        return self._normalize_df(self._coerce_to_polars(result, f"{module_name}.{fetcher_name}"))

    @staticmethod
    def _coerce_to_polars(result: Any, where: str = "fetcher") -> pl.DataFrame:
        """フェッチャー戻り値を pl.DataFrame に正規化する（pandas も受け付ける）。"""
        if isinstance(result, pl.DataFrame):
            return result
        # pandas DataFrame のダックタイピング（yfinance系）
        if hasattr(result, "to_dict") and hasattr(result, "empty"):
            if result.empty:
                return pl.DataFrame()
            try:
                return pl.from_pandas(result)
            except Exception:  # noqa: BLE001
                # pyarrow 不在等で from_pandas が失敗する場合は dict 経由で変換
                return pl.DataFrame({str(k): list(v.values()) for k, v in result.to_dict().items()})
        raise TypeError(f"{where} must return a DataFrame, got {type(result).__name__}")
