import importlib.util
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType
from typing import Any

import polars as pl

from .cache_manager import CacheManager


class OpenDataHub:
    """
    opendata-skill の各種フェッチャーを統合管理するハブよ。
    個別スクリプトを意識せずに、このハブから銀河級のデータ取得ができるわ。
    キャッシュ機能も搭載して、再取得の無駄を徹底的に排除してやるわ！
    """

    def __init__(self, cache_dir: str = ".cache") -> None:
        self.scripts_dir: Path = Path(__file__).resolve().parent
        self.fetchers: dict[str, Path] = self._discover_fetchers()
        self.cache = CacheManager(cache_dir=cache_dir)

    def _discover_fetchers(self) -> dict[str, Path]:
        """scripts ディレクトリ内のフェッチャーを自動検出するわ"""
        fetchers: dict[str, Path] = {}
        for file in self.scripts_dir.glob("*_fetcher.py"):
            name = file.name.replace("_fetcher.py", "")
            fetchers[name] = file
        return fetchers

    def _load_module(self, name: str) -> ModuleType:
        """フェッチャーモジュールを動的にロードするわ"""
        if name not in self.fetchers:
            raise ValueError(
                f"❌ Unknown fetcher: {name}. Available: {list(self.fetchers.keys())}"
            )

        spec = importlib.util.spec_from_file_location(
            f"opendata_{name}", self.fetchers[name]
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load spec for {name}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def get_many(
        self, specs: list[dict[str, Any]], max_workers: int = 8
    ) -> dict[str, pl.DataFrame]:
        """複数ソースを並列に取得する（I/Oバウンドなのでスレッドで十分）。

        specs: [{"label": str, "method": "get_xxx", "kwargs": {...}}, ...]
        戻り値: {label: DataFrame}。個々の失敗は隔離し、その label は空DFになる
        （1ソースのAPI障害が全体を巻き込まないようにする）。
        """
        def _run(spec: dict[str, Any]) -> tuple[str, pl.DataFrame]:
            label = spec["label"]
            try:
                fn = getattr(self, spec["method"])
                df = fn(**spec.get("kwargs", {}))
                return label, df if isinstance(df, pl.DataFrame) else pl.DataFrame()
            except Exception as e:  # noqa: BLE001 - 失敗を隔離して全体を守る
                print(f"[get_many] '{label}' ({spec.get('method')}) failed: {e}")
                return label, pl.DataFrame()

        results: dict[str, pl.DataFrame] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            for label, df in ex.map(_run, specs):
                results[label] = df
        return results

    def get_weather(self, lat: float, lon: float, **kwargs: Any) -> pl.DataFrame:
        """気象データを取得するわ (Open-Meteo)"""
        params = {"lat": lat, "lon": lon, **kwargs}
        cached = self.cache.get("weather", params)
        if cached is not None:
            return cached

        df = self._fetch_to_df(
            "meteo", "fetch_open_meteo",
            {"latitude": lat, "longitude": lon, **kwargs}, "temp_weather.csv",
        )

        if not self._is_degenerate(df):
            self.cache.set("weather", params, df, ttl_hours=24)
        return df

    def get_economic(
        self, indicators: list[str], countries: str = "all", **kwargs: Any
    ) -> pl.DataFrame:
        """世界銀行から経済指標を取得するわ"""
        params = {"indicators": sorted(indicators), "countries": countries, **kwargs}
        cached = self.cache.get("worldbank", params)
        if cached is not None:
            return cached

        df = self._fetch_to_df(
            "worldbank", "fetch_worldbank_data",
            {"indicators": indicators, "countries": countries, **kwargs}, "temp_econ.csv",
        )

        if not self._is_degenerate(df):
            self.cache.set("worldbank", params, df, ttl_hours=168) # 1 week
        return df

    def get_trends(
        self, keywords: list[str], geo: str = "JP", **kwargs: Any
    ) -> pl.DataFrame:
        """Googleトレンドを取得するわ"""
        params = {"keywords": sorted(keywords), "geo": geo, **kwargs}
        cached = self.cache.get("trends", params)
        if cached is not None:
            return cached

        df = self._fetch_to_df(
            "trends", "fetch_google_trends",
            {"keywords": keywords, "geo": geo, **kwargs}, "temp_trends.csv",
        )

        if not self._is_degenerate(df):
            self.cache.set("trends", params, df, ttl_hours=24)
        return df

    def get_freight(
        self,
        tickers: str = "BDRY",
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: Any,
    ) -> pl.DataFrame:
        """物流・海運コスト指標を取得するわ"""
        params = {"tickers": tickers, "start": start_date, "end": end_date, **kwargs}
        cached = self.cache.get("freight", params)
        if cached is not None:
            return cached

        df = self._fetch_to_df(
            "freight", "fetch_freight_data",
            {"tickers": tickers, "start_date": start_date, "end_date": end_date, **kwargs},
            "temp_freight.csv",
        )

        if not self._is_degenerate(df):
            self.cache.set("freight", params, df, ttl_hours=24)
        return df

    def get_fred(
        self,
        series_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: Any,
    ) -> pl.DataFrame:
        """FREDからマクロ経済指標を取得するわ"""
        params = {"id": series_id, "start": start_date, "end": end_date, **kwargs}
        cached = self.cache.get("fred", params)
        if cached is not None:
            return cached

        df = self._fetch_to_df(
            "fred", "fetch_fred_data",
            {"series_id": series_id, "start_date": start_date, "end_date": end_date, **kwargs},
            f"temp_fred_{series_id}.csv",
        )

        if not self._is_degenerate(df):
            self.cache.set("fred", params, df, ttl_hours=168)
        return df

    def get_yahoo(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: Any,
    ) -> pl.DataFrame:
        """Yahoo Financeから市場データを取得するわ"""
        params = {"symbol": symbol, "start": start_date, "end": end_date, **kwargs}
        cached = self.cache.get("yahoo", params)
        if cached is not None:
            return cached

        temp_csv = f"temp_yahoo_{symbol.replace('=', '_').replace('^', '_')}.csv"
        df = self._fetch_to_df(
            "yahoo", "fetch_yahoo_finance",
            {"tickers": symbol, "start_date": start_date, "end_date": end_date, **kwargs},
            temp_csv,
        )

        if not self._is_degenerate(df):
            self.cache.set("yahoo", params, df, ttl_hours=12) # Market data changes often
        return df

    def get_oecd(
        self,
        dataset: str,
        countries: str = "all",
        start_year: int | None = None,
        end_year: int | None = None,
        **kwargs: Any
    ) -> pl.DataFrame:
        """OECDから詳細な経済統計（QNA/SNA/MEI等）を取得するわ"""
        params = {"dataset": dataset, "countries": countries, "start": start_year, "end": end_year, **kwargs}
        cached = self.cache.get("oecd", params)
        if cached is not None:
            return cached

        df = self._fetch_to_df(
            "oecd", "fetch_oecd_data",
            {"dataset_code": dataset, "countries": countries,
             "start_year": start_year, "end_year": end_year, **kwargs},
            f"temp_oecd_{dataset.lower()}.csv",
        )

        if not self._is_degenerate(df):
            self.cache.set("oecd", params, df, ttl_hours=720) # 30 days
        return df

    def get_estat(
        self, stats_data_id: str, app_id: str | None = None, **kwargs: Any
    ) -> pl.DataFrame:
        """e-Statから日本の公的統計を取得するわ"""
        params = {"id": stats_data_id, **kwargs}
        cached = self.cache.get("estat", params)
        if cached is not None:
            return cached

        try:
            from api_utils import require_api_key
        except ImportError:
            from .api_utils import require_api_key

        app_id = app_id or require_api_key("ESTAT_API_KEY", "e-Stat", "https://www.e-stat.go.jp/api/")
        df = self._fetch_to_df(
            "estat", "fetch_estat_data",
            {"app_id": app_id, "stats_data_id": stats_data_id, **kwargs},
            f"temp_estat_{stats_data_id}.csv",
        )

        if not self._is_degenerate(df):
            self.cache.set("estat", params, df, ttl_hours=720)
        return df

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
        """指定された全18産業に関連するコモディティ価格や為替のプロキシ指標を取得するわ"""
        if industry not in self.INDUSTRY_COMMODITY_MAP:
            raise ValueError(f"❌ Unknown industry: {industry}. Available: {list(self.INDUSTRY_COMMODITY_MAP.keys())}")

        tickers = " ".join(self.INDUSTRY_COMMODITY_MAP[industry])
        return self.get_yahoo(symbol=tickers, start_date=start_date, end_date=end_date, **kwargs)

    def get_global_macro(
        self, region: str, indicators: list[str] | None = None, start_year: int | None = None, end_year: int | None = None, **kwargs: Any
    ) -> pl.DataFrame:
        """CNやEUなどのグローバルマクロ指標をプリセットで取得するわ"""
        region_map = {
            "CN": "CHN",
            "EU": "EUU",
            "US": "USA",
            "JP": "JPN",
            "EA": "EMU" # Euro Area
        }
        code = region_map.get(region.upper(), region)
        inds = indicators or ["gdp", "inflation", "unemployment"]

        return self.get_economic(indicators=inds, countries=code, start_year=start_year, end_year=end_year, **kwargs)

    def get_china_macro(self, start_year: int | None = None, end_year: int | None = None, **kwargs: Any) -> pl.DataFrame:
        """中国 (NBS相当) の主要マクロ指標をワンクリックで取得するプリセットよ"""
        return self.get_global_macro(
            region="CHN",
            indicators=["gdp_growth", "inflation", "unemployment", "gni"],
            start_year=start_year,
            end_year=end_year,
            **kwargs
        )

    def get_europe_macro(self, start_year: int | None = None, end_year: int | None = None, **kwargs: Any) -> pl.DataFrame:
        """欧州 (Eurostat相当) の主要マクロ指標をワンクリックで取得するプリセットよ"""
        # 欧州全体 (EUU) とユーロ圏 (EMU) を対象に取得
        return self.get_global_macro(
            region="EUU,EMU",
            indicators=["gdp_growth", "inflation", "unemployment", "gdp"],
            start_year=start_year,
            end_year=end_year,
            **kwargs
        )

    def get_us_macro(self, start_year: int | None = None, end_year: int | None = None, **kwargs: Any) -> pl.DataFrame:
        """米国 (BEA/BLS相当) の主要マクロ指標をワンクリックで取得するプリセットよ"""
        return self.get_global_macro(
            region="USA",
            indicators=["gdp_growth", "inflation", "unemployment", "gdp"],
            start_year=start_year,
            end_year=end_year,
            **kwargs
        )

    # ========================================================================
    # v2.1 Extensions: SCM/需要予測向け先行指標・リスク・補完フェッチャー
    # ========================================================================

    def _cached_fetch(
        self,
        module_name: str,
        fetcher_name: str,
        cache_key: str,
        cache_params: dict[str, Any],
        ttl_hours: int,
        temp_csv: str,
        call_kwargs: dict[str, Any],
    ) -> pl.DataFrame:
        """キャッシュ確認 → フェッチ（戻り値DF優先/CSVフォールバック）→ キャッシュ保存の共通処理"""
        cached = self.cache.get(cache_key, cache_params)
        if cached is not None:
            return cached
        df = self._fetch_to_df(module_name, fetcher_name, call_kwargs, temp_csv)
        if not self._is_degenerate(df):
            self.cache.set(cache_key, cache_params, df, ttl_hours=ttl_hours)
        return df

    def get_pmi(self, series: str = "us_new_orders", **kwargs: Any) -> pl.DataFrame:
        """PMI・製造業先行指標 (FRED経由: 新規受注/OECD CLI/政策不確実性等)"""
        return self._cached_fetch(
            "pmi", "fetch_pmi_data", "pmi",
            {"series": series, **kwargs}, 168,
            f"temp_pmi_{series}.csv", {"series": series, **kwargs},
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
            f"temp_comtrade_{reporter}_{partner}_{hs_code}.csv", call,
        )

    def get_eia(self, series: str = "crude_stocks", **kwargs: Any) -> pl.DataFrame:
        """EIA 米エネルギー需給 (石油・ガス在庫、精製稼働率)"""
        return self._cached_fetch(
            "eia", "fetch_eia_data", "eia",
            {"series": series, **kwargs}, 24,
            f"temp_eia_{series}.csv", {"series": series, **kwargs},
        )

    def get_gdelt(self, query: str = "supply chain disruption", theme: str | None = None, **kwargs: Any) -> pl.DataFrame:
        """GDELT 地政学・SC断絶イベントデータ (APIキー不要)"""
        return self._cached_fetch(
            "gdelt", "fetch_gdelt_data", "gdelt",
            {"query": query, "theme": theme, **kwargs}, 6,
            "temp_gdelt.csv", {"query": query, "theme": theme, **kwargs},
        )

    def get_ais(self, port: str = "shanghai", provider: str = "auto", **kwargs: Any) -> pl.DataFrame:
        """AIS / 港湾混雑データ (BDIの先行指標)"""
        return self._cached_fetch(
            "ais", "fetch_ais_data", "ais",
            {"port": port, "provider": provider, **kwargs}, 2,
            f"temp_ais_{port}.csv", {"port": port, "provider": provider, **kwargs},
        )

    def get_agri(self, source: str = "faostat", commodity: str = "corn", **kwargs: Any) -> pl.DataFrame:
        """USDA / FAOSTAT 農業・食品データ"""
        return self._cached_fetch(
            "usda", "fetch_agri_data", "usda",
            {"source": source, "commodity": commodity, **kwargs}, 720,
            f"temp_agri_{source}_{commodity}.csv",
            {"source": source, "commodity": commodity, **kwargs},
        )

    def get_semicon(self, series: str = "us_semi_shipments", **kwargs: Any) -> pl.DataFrame:
        """半導体業界指標 (出荷/在庫/B2B比)"""
        # book_to_bill のみ compute_book_to_bill を呼ぶ特殊ケース
        if series == "book_to_bill":
            return self._cached_fetch(
                "semicon", "compute_book_to_bill", "semicon",
                {"series": series, **kwargs}, 168,
                f"temp_semi_{series}.csv", kwargs,
            )
        return self._cached_fetch(
            "semicon", "fetch_semicon_data", "semicon",
            {"series": series, **kwargs}, 168,
            f"temp_semi_{series}.csv", {"series": series, **kwargs},
        )

    def get_entsoe(self, data_type: str = "load_actual", country: str = "DE", **kwargs: Any) -> pl.DataFrame:
        """ENTSO-E 欧州電力需給データ"""
        call = {"data_type": data_type, "country": country, **kwargs}
        return self._cached_fetch(
            "entsoe", "fetch_entsoe_data", "entsoe", call, 6,
            f"temp_entsoe_{country}_{data_type}.csv", call,
        )

    def get_usgs_earthquakes(self, min_magnitude: float = 4.5, **kwargs: Any) -> pl.DataFrame:
        """USGS グローバル地震データ (海外拠点リスク)"""
        return self._cached_fetch(
            "usgs", "fetch_usgs_earthquakes", "usgs",
            {"min_mag": min_magnitude, **kwargs}, 1,
            "temp_usgs.csv", {"min_magnitude": min_magnitude, **kwargs},
        )

    def get_firms(self, region: str = "us_west", source: str = "viirs_n", **kwargs: Any) -> pl.DataFrame:
        """NASA FIRMS 山火事リアルタイム衛星データ"""
        call = {"region": region, "source": source, **kwargs}
        return self._cached_fetch(
            "firms", "fetch_firms_data", "firms", call, 3,
            f"temp_firms_{region}.csv", call,
        )

    def get_official_fx(self, source: str = "ecb", currency: str = "JPY", **kwargs: Any) -> pl.DataFrame:
        """ECB / Frankfurter-JPY 為替レート (公的参照)"""
        call = {"source": source, "currency": currency, **kwargs}
        return self._cached_fetch(
            "official_fx", "fetch_official_fx", "official_fx", call, 24,
            f"temp_official_fx_{source}_{currency}.csv", call,
        )

    def get_edinet_financials(self, edinet_code: str, period: str = "annual", years: int | None = None, **kwargs: Any) -> pl.DataFrame:
        """EDINET DBから財務データを取得するわ (edinetdb利用)"""
        call = {"edinet_code": edinet_code, "period": period, "years": years, **kwargs}
        return self._cached_fetch(
            "edinet", "fetch_edinet_financials", "edinet_financials", call, 24,
            f"temp_edinet_{edinet_code}_{period}.csv", call,
        )

    def get_edinet_ratios(self, edinet_code: str, **kwargs: Any) -> pl.DataFrame:
        """EDINET DBから財務比率データを取得するわ (edinetdb利用)"""
        call = {"edinet_code": edinet_code, **kwargs}
        return self._cached_fetch(
            "edinet", "fetch_edinet_ratios", "edinet_ratios", call, 24,
            f"temp_edinet_ratios_{edinet_code}.csv", call,
        )

    # ========================================================================
    # 日本の先行指標プリセット (景気動向指数 / 短観 / 訪日外客数)
    # ========================================================================

    def get_boj_tankan(self, series: str = "tankan_large_mfg", **kwargs: Any) -> pl.DataFrame:
        """日銀 短観の業況判断DIなどを取得するわ (BOJ時系列API・キー不要)"""
        call = {"series": series, **kwargs}
        return self._cached_fetch(
            "boj", "fetch_boj_data", "boj", call, 168,
            f"temp_boj_{series}.csv", call,
        )

    def get_keiki_di(self, **kwargs: Any) -> pl.DataFrame:
        """内閣府 景気動向指数 (CI/DI、先行指数を含む) を e-Stat 経由で取得するわ。

        表章項目=CI指数 × 系列=先行指数 などはメタの名称列で絞り込めるわよ。
        """
        return self.get_estat(stats_data_id="0003446461", **kwargs)

    def get_inbound_visitors(self, **kwargs: Any) -> pl.DataFrame:
        """訪日外客数 (港別 入国外国人の国籍・地域、月次) を e-Stat 経由で取得するわ。

        港 × 国籍・地域 の粒度なので、国別月次合計は港次元で集計してね。
        """
        return self.get_estat(stats_data_id="0003449064", **kwargs)

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

        CSV経由・戻り値経由のどちらの取得経路でも同じ正規化を適用する。
        複数列が同じ正規化名に衝突する場合は最初の1列だけ採用し、rename の
        DuplicateError（→従来は黙って空DF化）を防ぐ。冪等。
        """
        mapping: dict[str, str] = {}
        used: set[str] = set()

        def _claim(col: str, target: str) -> None:
            if target not in used:
                mapping[col] = target
                used.add(target)

        for col in df.columns:
            c_low = col.lower()
            if c_low in ["date", "time", "時間"]:
                _claim(col, "date")
            elif c_low in ["value", "close", "adj close", "値"]:
                _claim(col, "value")

        return df.rename(mapping) if mapping else df

    def _fetch_to_df(
        self, module_name: str, fetcher_name: str, call_kwargs: dict[str, Any], temp_csv: str
    ) -> pl.DataFrame:
        """フェッチャーを呼び、戻り値の DataFrame を優先消費する。

        戻り値が None のフェッチャー（CSV書き出しのみ）の場合だけ temp CSV に
        フォールバックする。戻り値経由なら CSV ラウンドトリップの型喪失
        （日付→文字列化など）を避けられる。

        temp_csv は呼び出し側の固定名を信用せず、毎回ユニーク化する。get_many の
        並列実行で同名フェッチャーが共有CWDの同じ一時ファイルを取り合う競合
        （片方が他方のデータを読む/片方が空になる）を防ぐ。
        """
        stem = os.path.basename(temp_csv).removesuffix(".csv")
        temp_csv = f"{stem}_{uuid.uuid4().hex}.csv"

        m = self._load_module(module_name)
        fetcher = getattr(m, fetcher_name)
        result = fetcher(output_file=temp_csv, **call_kwargs)

        df = self._coerce_to_polars(result)
        if df is not None:
            # 戻り値を採用。CSV を書いていたら掃除する。
            if os.path.exists(temp_csv):
                os.remove(temp_csv)
            return self._normalize_df(df)

        # None 戻り → CSV フォールバック
        return self._csv_to_df(temp_csv)

    @staticmethod
    def _coerce_to_polars(result: Any) -> pl.DataFrame | None:
        """フェッチャー戻り値を pl.DataFrame に正規化する。None/空でない場合のみ返す。"""
        if result is None:
            return None
        if isinstance(result, pl.DataFrame):
            return result if not result.is_empty() else None
        # pandas DataFrame のダックタイピング（yfinance系）
        if hasattr(result, "to_dict") and hasattr(result, "empty"):
            if result.empty:
                return None
            try:
                return pl.from_pandas(result)
            except Exception:  # noqa: BLE001
                # pyarrow 不在等で from_pandas が失敗する場合は dict 経由で変換
                return pl.DataFrame({str(k): list(v.values()) for k, v in result.to_dict().items()})
        return None

    def _csv_to_df(self, path: str) -> pl.DataFrame:
        """一時 CSV を Polars DF に変換して削除するわ。カラム名の標準化も行うわよ。

        ファイルが存在しない場合のみ「データ無し」として空DFを返す。
        ファイルは在るのにパースに失敗した場合は、空データと誤認させず例外を送出する
        （取得失敗を黙って欠損covariateに化けさせない）。
        """
        if not os.path.exists(path):
            return pl.DataFrame()

        try:
            df = pl.read_csv(path)
            return self._normalize_df(df)
        finally:
            if os.path.exists(path):
                os.remove(path)
