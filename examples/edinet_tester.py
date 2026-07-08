import sys
from pathlib import Path

from dotenv import load_dotenv

# 親ディレクトリをパスに追加してモジュールを読み込めるようにする
sys.path.append(str(Path(__file__).parent.parent))

# 環境変数を読み込む
load_dotenv()

from scripts.opendata_hub import OpenDataHub


def main():
    hub = OpenDataHub()
    print("🚀 EDINET DB からトヨタ自動車 (E02144) の財務データを取得中...")

    try:
        # トヨタ (E02144) の過去5年の財務データを取得
        df_fin = hub.get_edinet_financials("E02144", years=5)
        print("\n📊 財務データ (Financials):")
        print(df_fin)

        print("\n🚀 続いて財務比率データを取得中...")
        df_ratios = hub.get_edinet_ratios("E02144")
        print("\n📈 財務比率 (Ratios):")
        print(df_ratios)

    except Exception as e:
        print(f"\n❌ エラーが発生したわ: {type(e).__name__} - {e}")
        print("💡 ヒント: EDINET DBのAPIキーが設定されているか確認してね (`edinetdb auth login` または `EDINETDB_API_KEY` の設定)")

if __name__ == "__main__":
    main()
