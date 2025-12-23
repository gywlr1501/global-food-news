import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from datetime import datetime, timedelta
import re
import time

# ---------------------------------------------------------
# 1. API 설정
# ---------------------------------------------------------
# [중요] secrets.toml 파일에서 키를 가져옵니다.
# 깃허브에 올릴 때 이 부분 덕분에 키가 보호됩니다.
if "food_api_key" in st.secrets:
    API_KEY = st.secrets["food_api_key"]
else:
    # 로컬 테스트용 (혹시 secrets 파일 못 찾을 경우 대비)
    # 깃허브 올릴 땐 이 줄이 실행되지 않고 위의 secrets가 실행됩니다.
    API_KEY = "WZxom7cW5aEccPhTnj8mlyGFdNOv2nYw"

API_URL = "https://api.foodinfo.or.kr/api/foodinfo/daily/json"

# 국가명 한글 -> 영어 매핑
COUNTRY_MAPPING = {
    "중국": "China", "일본": "Japan", "미국": "United States", 
    "프랑스": "France", "베트남": "Vietnam", "독일": "Germany", 
    "이탈리아": "Italy", "영국": "United Kingdom", "캐나다": "Canada",
    "호주": "Australia", "태국": "Thailand", "인도": "India",
    "대한민국": "South Korea", "한국": "South Korea", "대만": "Taiwan",
    "스페인": "Spain", "러시아": "Russia", "브라질": "Brazil",
    "인도네시아": "Indonesia", "필리핀": "Philippines", "네덜란드": "Netherlands",
    "벨기에": "Belgium", "튀르키예": "Turkey", "터키": "Turkey"
}

def remove_html_tags(text):
    """HTML 태그 제거 및 텍스트 정리"""
    if pd.isna(text):
        return ""
    clean = re.compile('<.*?>')
    text = re.sub(clean, '', str(text))
    return text.replace('&nbsp;', ' ').replace('&lt;', '<').replace('&gt;', '>').strip()

@st.cache_data(ttl=3600)
def fetch_food_data(start_date, end_date):
    """
    100개 제한을 우회하기 위해 반복문으로 데이터를 수집합니다.
    """
    bgnde = start_date.strftime("%Y%m%d")
    endde = end_date.strftime("%Y%m%d")
    
    all_data = []
    max_items = 500
    batch_size = 100

    progress_bar = st.progress(0)
    status_text = st.empty()

    try:
        for i in range(5):
            start_index = (i * batch_size) + 1
            end_index = (i + 1) * batch_size
            
            status_text.text(f"데이터 가져오는 중... ({start_index} ~ {end_index}번째)")
            
            params = {
                "apiKey": API_KEY,
                "bgnde": bgnde,
                "endde": endde,
                "startIndex": start_index,
                "endIndex": end_index
            }

            response = requests.get(API_URL, params=params)
            response.raise_for_status()
            data = response.json()
            
            if not isinstance(data, dict) or 'ITEMS' not in data or not data['ITEMS']:
                break
                
            all_data.extend(data['ITEMS'])
            progress_bar.progress((i + 1) / 5)
            time.sleep(0.1)

        progress_bar.empty()
        status_text.empty()

        if not all_data:
            return pd.DataFrame()

        df = pd.DataFrame(all_data)

        df = df.rename(columns={
            'TITLE': '제품명',
            'COUNTRY': '국가',
            'INFO_TYPE': '구분',
            'CONTENT': '상세내용',
            'REGISTRATION_DATE': '등록일',
            'ORIGINAL_URL': '원문링크'
        })
        
        df = df.sort_values(by='등록일', ascending=False)
        
        if '상세내용' in df.columns:
            df['상세내용'] = df['상세내용'].apply(remove_html_tags)
        
        df['Country_EN'] = df['국가'].map(COUNTRY_MAPPING).fillna(df['국가'])
        
        return df

    except Exception as e:
        st.error(f"⚠️ 데이터 요청 중 오류: {e}")
        return pd.DataFrame(all_data) if all_data else pd.DataFrame()

# ---------------------------------------------------------
# 2. 웹 대시보드 UI 구성
# ---------------------------------------------------------
st.set_page_config(page_title="식품안전정보원 최신 회수 정보", layout="wide")

with st.sidebar:
    st.header("🔍 검색 기간 설정")
    
    today = datetime.now()
    if today.year >= 2025:
        safe_end_date = datetime(2024, 12, 31)
    else:
        safe_end_date = today

    safe_start_date = safe_end_date - timedelta(days=90)

    start_date_input = st.date_input("시작일", safe_start_date)
    end_date_input = st.date_input("종료일", safe_end_date)
    
    if st.button("데이터 불러오기"):
        st.cache_data.clear()

df = fetch_food_data(start_date_input, end_date_input)

st.title(f"🌏 식품안전정보원 실시간 현황")
st.caption(f"조회 기간: {start_date_input} ~ {end_date_input}")

if df.empty:
    st.warning("데이터가 없습니다.")
    st.stop()
else:
    st.success(f"✅ 데이터 로드 완료! 총 **{len(df)}건**")

tab1, tab2 = st.tabs(["📋 최신 뉴스 리스트", "🗺️ 세계 지도 시각화"])

with tab1:
    st.header("🚨 최신 위해식품 정보")
    
    col1, col2 = st.columns(2)
    with col1:
        types = list(df['구분'].unique())
        filter_type = st.multiselect("정보 구분", types, default=types)
    with col2:
        countries = list(df['국가'].unique())
        filter_country = st.multiselect("국가 선택", countries, default=countries)

    filtered_df = df[
        (df['구분'].isin(filter_type)) & 
        (df['국가'].isin(filter_country))
    ]

    st.dataframe(
        filtered_df[['등록일', '구분', '국가', '제품명', '상세내용']],
        use_container_width=True,
        hide_index=True,
        height=600
    )

with tab2:
    st.header("🌍 국가별 이슈 분포")
    
    map_data = filtered_df.groupby(['Country_EN', '국가', '구분']).size().reset_index(name='건수')
    
    fig = px.scatter_geo(
        map_data,
        locations="Country_EN",
        locationmode='country names',
        color="구분",
        hover_name="국가",
        size="건수",
        projection="natural earth",
        title=f"국가별 발생 분포",
        template="plotly_white",
        hover_data={"Country_EN": False, "건수": True},
        size_max=40
    )

    fig.update_geos(
        showcoastlines=True, coastlinecolor="Black",
        showland=True, landcolor="#f4f4f4",
        showocean=True, oceancolor="#e3f2fd",
        showcountries=True, countrycolor="white"
    )
    
    fig.update_layout(height=600, margin={"r":0,"t":40,"l":0,"b":0})
    st.plotly_chart(fig, use_container_width=True)

    st.divider()
    
    c1, c2 = st.columns([1, 2])
    with c1:
        st.subheader("📌 국가별 요약")
        available_countries = filtered_df['국가'].unique()
        if len(available_countries) > 0:
            selected_country = st.selectbox("국가 선택:", available_countries)
            country_data = filtered_df[filtered_df['국가'] == selected_country]
            
            st.info(f"**{selected_country}** 발생 건수: **{len(country_data)}건**")
            st.metric("가장 최근 발생일", country_data['등록일'].max())

    with c2:
        if len(available_countries) > 0:
            st.subheader(f"📄 {selected_country} 최신 이슈")
            for i, row in country_data.head(5).iterrows():
                with st.expander(f"[{row['등록일']}] {row['제품명']}"):
                    st.write(f"**내용:** {row['상세내용']}")
                    if row['원문링크']:
                        st.markdown(f"[🔗 원문 보러가기]({row['원문링크']})")