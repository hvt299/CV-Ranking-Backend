import time
import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_URL = "https://tinhthanhpho.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0 Safari/537.36"
}

session = requests.Session()
session.headers.update(HEADERS)


def get_soup(url):
    while True:
        try:
            r = session.get(url, timeout=30)
            r.raise_for_status()
            return BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            print(f"Lỗi tải {url}: {e}")
            time.sleep(3)


def get_rows(soup):
    table = soup.find("table")
    if not table:
        return []
    tbody = table.find("tbody")
    if not tbody:
        return []
    return tbody.find_all("tr")


def clean(text):
    return " ".join(text.strip().split())


# =====================================================
# DỮ LIỆU CŨ
# =====================================================

provinces = []
districts = []
wards = []

print("Đang crawl tỉnh/thành...")

soup = get_soup(f"{BASE_URL}/search/provinces")

for tr in get_rows(soup):
    tds = tr.find_all("td")

    province_code = clean(tds[0].text)
    province_name = clean(tds[1].text)
    province_type = clean(tds[2].text)

    district_url = urljoin(BASE_URL, tds[3].find("a")["href"])

    provinces.append({
        "province_code": province_code,
        "province_name": province_name,
        "province_type": province_type
    })

    print(f" -> {province_name}")

    soup_district = get_soup(district_url)

    for dtr in get_rows(soup_district):
        dtds = dtr.find_all("td")

        if len(dtds) != 4:
            continue

        district_code = clean(dtds[0].get_text())
        district_name = clean(dtds[1].get_text())
        district_type = clean(dtds[2].get_text())

        link = dtds[3].find("a")
        if link is None:
            continue

        ward_url = urljoin(BASE_URL, link["href"])

        districts.append({
            "province_code": province_code,
            "province_name": province_name,
            "district_code": district_code,
            "district_name": district_name,
            "district_type": district_type
        })

        soup_ward = get_soup(ward_url)

        for wtr in get_rows(soup_ward):
            wtds = wtr.find_all("td")

            if len(wtds) != 4:
                print(f"Skip row tại {ward_url}")
                continue

            ward_code = clean(wtds[0].get_text())
            ward_name = clean(wtds[1].get_text())
            ward_type = clean(wtds[2].get_text())
            full_address = clean(wtds[3].get_text())

            wards.append({
                "province_code": province_code,
                "province_name": province_name,
                "district_code": district_code,
                "district_name": district_name,
                "ward_code": ward_code,
                "ward_name": ward_name,
                "ward_type": ward_type,
                "full_address": full_address
            })


# =====================================================
# DỮ LIỆU MỚI (SAU SÁP NHẬP)
# =====================================================

new_provinces = []
new_wards = []

print("Đang crawl tỉnh/thành mới...")

soup = get_soup(f"{BASE_URL}/search/new-provinces")

for tr in get_rows(soup):
    tds = tr.find_all("td")

    province_code = clean(tds[0].text)
    province_name = clean(tds[1].text)
    province_type = clean(tds[2].text)

    ward_url = urljoin(BASE_URL, tds[3].find("a")["href"])

    new_provinces.append({
        "province_code": province_code,
        "province_name": province_name,
        "province_type": province_type
    })

    print(f" -> {province_name}")

    soup_ward = get_soup(ward_url)

    for wtr in get_rows(soup_ward):
        wtds = wtr.find_all("td")

        if len(wtds) != 4:
            print(f"Skip row tại {ward_url}")
            continue

        ward_code = clean(wtds[0].get_text())
        ward_name = clean(wtds[1].get_text())
        ward_type = clean(wtds[2].get_text())
        full_address = clean(wtds[3].get_text())

        new_wards.append({
            "province_code": province_code,
            "province_name": province_name,
            "ward_code": ward_code,
            "ward_name": ward_name,
            "ward_type": ward_type,
            "full_address": full_address
        })


# =====================================================
# LƯU CSV
# =====================================================

pd.DataFrame(provinces).to_csv(
    "provinces.csv",
    index=False,
    encoding="utf-8-sig"
)

pd.DataFrame(districts).to_csv(
    "districts.csv",
    index=False,
    encoding="utf-8-sig"
)

pd.DataFrame(wards).to_csv(
    "wards.csv",
    index=False,
    encoding="utf-8-sig"
)

pd.DataFrame(new_provinces).to_csv(
    "new_provinces.csv",
    index=False,
    encoding="utf-8-sig"
)

pd.DataFrame(new_wards).to_csv(
    "new_wards.csv",
    index=False,
    encoding="utf-8-sig"
)

print("\nHoàn thành.")
print(f"Provinces: {len(provinces)}")
print(f"Districts: {len(districts)}")
print(f"Wards: {len(wards)}")
print(f"New Provinces: {len(new_provinces)}")
print(f"New Wards: {len(new_wards)}")