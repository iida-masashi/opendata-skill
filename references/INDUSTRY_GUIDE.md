# Industry-Specific Open Data Guide

This guide maps available Open Data APIs to specific industries and business use cases.
Use this to identify which data sources are relevant to your sector.

## 🏭 Manufacturing (製造業)

| Use Case | Recommended Data Source | Script | Description |
| :--- | :--- | :--- | :--- |
| **Production Planning** | **e-Stat (Industrial Production)** | `estat_fetcher.py` | Indices of Industrial Production (鉱工業生産指数) to gauge market trends. |
| **Cost Management** | **TEPCO / METI** | `power_fetcher.py` | Electricity usage trends for energy cost optimization. |
| **Supply Chain Risk** | **J-SHIS** | `jshis_fetcher.py` | Earthquake risk assessment for factory locations. |
| **Raw Material Costs** | **Yahoo Finance** | `yahoo_fetcher.py` | Commodity prices (Oil, Metals) and FX rates (USD/JPY). |
| **Trade Analysis** | **Trade Statistics (e-Stat)** | `estat_fetcher.py` | Import/Export volume of raw materials and parts. |
| **Demand Leading Indicator** | **BOJ Tankan** | `boj_fetcher.py` | Business conditions DI (大企業製造業 業況判断DI) — a leading signal for B2B demand and capex. |
| **Business Cycle Timing** | **Cabinet Office CI/DI** | `get_keiki_di` (e-Stat) | Composite/Diffusion Index leading series (景気動向指数 先行指数) for cycle turning points. |

## 🚚 Logistics & SCM (物流・サプライチェーン)

| Use Case | Recommended Data Source | Script | Description |
| :--- | :--- | :--- | :--- |
| **Route Optimization** | **GSI Maps** | `gsi_fetcher.py` | Geocoding addresses to coordinates for route planning. |
| **Warehouse Location** | **MLIT Land Price** | `mlit_fetcher.py` | Land prices and transaction data for site selection. |
| **Delivery Planning** | **Open-Meteo** | `meteo_fetcher.py` | Weather forecasts (Rain, Snow, Wind) impacting delivery schedules. |
| **Address Cleansing** | **ZipCloud** | `zipcode_fetcher.py` | Normalizing address data from zipcodes. |
| **Disaster Risk** | **River Info / J-SHIS** | `river_fetcher.py`, `jshis_fetcher.py` | Flood and earthquake risks for logistics hubs. |

## 🛒 Retail & Marketing (小売・マーケティング)

| Use Case | Recommended Data Source | Script | Description |
| :--- | :--- | :--- | :--- |
| **Demand Forecasting** | **Google Trends** | `trends_fetcher.py` | Search interest for products/brands to predict demand. |
| **Catchment Analysis** | **RESAS** | `resas_fetcher.py` | Population demographics and flow in specific regions. |
| **Store Opening** | **e-Stat (Census)** | `estat_fetcher.py` | Population density and household income data. |
| **Event Planning** | **Open-Meteo** | `meteo_fetcher.py` | Weather data to adjust inventory (e.g., umbrella sales). |
| **Competitor Analysis** | **Corporate Number** | `corp_fetcher.py` | Official corporate info of competitors. |
| **Inbound Demand** | **JNTO Visitors** | `get_inbound_visitors` (e-Stat) | Monthly foreign visitor arrivals by country (訪日外客数) — driver of tourism/duty-free demand. |

## 🏗️ Construction & Real Estate (建設・不動産)

| Use Case | Recommended Data Source | Script | Description |
| :--- | :--- | :--- | :--- |
| **Urban Planning** | **PLATEAU** | `plateau_fetcher.py` | 3D city models for simulation and visualization. |
| **Valuation** | **MLIT Land Price** | `mlit_fetcher.py` | Official land prices (Chika Koji) and transaction history. |
| **Site Safety** | **J-SHIS / River Info** | `jshis_fetcher.py`, `river_fetcher.py` | Hazard risks (Earthquake, Flood) for land development. |
| **Market Analysis** | **e-Stat (Housing Starts)** | `estat_fetcher.py` | Statistics on new housing construction starts. |

## 💹 Finance & Insurance (金融・保険)

| Use Case | Recommended Data Source | Script | Description |
| :--- | :--- | :--- | :--- |
| **Market Analysis** | **Yahoo Finance** | `yahoo_fetcher.py` | Real-time and historical stock/FX/crypto data. |
| **Macro Economy** | **World Bank / OECD** | `worldbank_fetcher.py`, `oecd_fetcher.py` | GDP, Inflation, Interest rates for global analysis. |
| **Business Sentiment** | **BOJ Tankan / Cabinet Office CI/DI** | `boj_fetcher.py`, `get_keiki_di` | Tankan DI and the Composite Index leading series for domestic cycle calls. |
| **Risk Assessment** | **J-SHIS** | `jshis_fetcher.py` | Earthquake probability for property insurance pricing. |
| **Corporate Due Diligence** | **Corporate Number** | `corp_fetcher.py` | Verification of corporate existence and basic info. |

## 🌾 Agriculture (農業)

| Use Case | Recommended Data Source | Script | Description |
| :--- | :--- | :--- | :--- |
| **Crop Planning** | **Open-Meteo** | `meteo_fetcher.py` | Historical weather data for yield prediction. |
| **Water Management** | **River Info** | `river_fetcher.py` | River discharge data for irrigation planning. |
| **Market Prices** | **e-Stat (MAFF)** | `estat_fetcher.py` | Wholesale market prices for vegetables and fruits. |

## 🏛️ Public Sector & Research (公共・研究)

| Use Case | Recommended Data Source | Script | Description |
| :--- | :--- | :--- | :--- |
| **Policy Making** | **e-Stat / RESAS** | `estat_fetcher.py`, `resas_fetcher.py` | Census and regional economy data for evidence-based policy. |
| **Environmental Study** | **Air Quality** | `air_quality_fetcher.py` | PM2.5, NO2 levels for environmental monitoring. |
| **Urban Transit** | **ODPT** | `odpt_fetcher.py` | Public transport data for smart city projects. |
| **Open Data Search** | **CKAN / e-Gov** | `ckan_fetcher.py` | Discovering new datasets across government agencies. |
