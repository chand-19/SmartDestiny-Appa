from playwright.sync_api import sync_playwright
from lxml import html
import time
import pandas as pd 
import re
import os

# Fungsi untuk scraping Google Maps berdasarkan kota dan kategori tertentu
def scrape_google_maps(city_name, category_name):
    # Inisialisasi daftar untuk menyimpan data yang diekstraksi
    extracted_data = []
    processed_urls = set()  # Melacak URL yang diproses

    with sync_playwright() as p:
        # Meluncurkan Edge browser
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Buka Google Maps
        page.goto("https://www.google.com/maps/?hl=en")
        print('Going to Google Maps')

        # Tunggu hingga elemen search box muncul
        search_box = 'input#searchboxinput'
        time.sleep(1)

        # Langkah 1: Mencari destinasi wisata
        page.locator(search_box)
        page.fill(search_box,f'{category_name}, {city_name}')

        # Mensimulasikan tombol enter
        page.press(search_box, "Enter")

        print(f'Searching places...')
        time.sleep(3)

        # Langkah 2: Melakukan zoom pada map
        try:
            page.wait_for_load_state("networkidle")
            while True:
                zoom_button = page.query_selector("//div[@id='zoom']//button[@aria-label='Zoom in']")
                if zoom_button:
                    is_disabled = zoom_button.get_attribute('disabled')
                    print(is_disabled)
                    if is_disabled == 'true':
                        print("Zoom button is disabled. Stopping...")
                        break

                    # Lanjut menekan tombol zoom
                    zoom_button.click()
                    print('Zooming in...')
                    time.sleep(0.2)
                else:
                    print("Zoom button not found. Stopping...")
                    break

        except Exception as e:
            print("No clickable button. Skip zooming the page...", e)

        # Langkah 3: Mengulangi item yang dapat diklik dan ekstrak datanya
        try:
            while True:
                clickable_items = page.query_selector_all("//div[@role='feed']//a[@aria-label and starts-with(@href, 'https://www.google.com/maps')]")
                if not clickable_items:
                    print("No more clickable items found.")
                    break

                # Scroll halaman untuk memuat item lebih banyak
                page.evaluate("document.querySelector('div[role=feed]').scrollTo(0, document.querySelector('div[role=feed]').scrollHeight)")
                print("Scrolling...")

                for index, item in enumerate(clickable_items):
                    href = item.get_attribute("href")
                    print(href)
                    if href in processed_urls:
                        # Lewati item yang sudah diproses
                        continue

                    print(f"Clicking item {index + 1}: ")
                    item.click()
                    processed_urls.add(href)

                    time.sleep(2)  # Memastikan konten telah dimuat sepenuhnya

                    # mengekstrak konten halaman
                    page_source = page.content()
                    tree = html.fromstring(page_source)

                    # Mengkstrak koordinat dari URL
                    current_url = page.url
                    match = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", current_url)
                    if match:
                        latitude = float(match.group(1))
                        longitude = float(match.group(2))
                    else:
                        latitude = None
                        longitude = None

                    # Mengkstrak data yang diinginkan menggunakan kueri yang lebih aman
                    place = tree.xpath("//h1[@class='DUwDvf lfPIob']/text()")
                    description = tree.xpath("//div[@class='y0K5Df']//div[contains(@class,'PYvSYb')]/text()")
                    address = tree.xpath("//button[@class='CsEnBe' and contains(@aria-label,'Address')]//div[contains(@class,'Io6YTe')]/text()")
                    price = tree.xpath("(//div[@class='drwWxc'])[1]/text()")
                    rating = tree.xpath("//div[contains(@class,'F7nice')]//span[contains(@aria-hidden,'true')]/text()")
                    review_count = tree.xpath('//span[contains(@aria-label, "reviews")]/text()')

                    # Menangani daftar kosong dan menetapkan default
                    place = place[0] if place else None
                    description = description[0] if description else None
                    address = address[0] if address else None
                    rating = float(rating[0]) if rating else None
                    review_count = int(re.sub(r'\D', '', review_count[0])) if review_count else 0 # Ekstrak digit dan konversi ke int

                    # Mengeliminasi tempat yang tidak sesuai alamatnya
                    if address and city_name.lower() not in address.lower():
                        print(f'{place} is not in {city_name}')
                        continue

                    # Membatalkan ekstraksi data jika tidak ada element berikut
                    if not description:
                        print("No description. Skip to the next place.")
                        continue
                    
                    # Membersihkan dan mengubah harga 
                    if price: 
                        price = price[0].replace('Rp', '').replace('.', '').replace(',', '.').strip() 
                        try: 
                            price = float(price) 
                        except ValueError: 
                                price = 0.0 # Default ke 0.0 jika konversi gagal 
                    else: price = 0.0

                    # Membersihkan dan menyusun data yang diekstraksi
                    data_entry = {
                        "Place": place,
                        "Description": description,
                        "Category": category_name,
                        "Address": address,
                        "City": city_name,
                        "Price": price,
                        "Rating": rating,
                        "Review_count": review_count,
                        "Latitude": latitude,
                        "Longitude": longitude,
                    }

                    # Navigasi ke tab kedua (About) untuk mengekstrak data tambahan
                    try:
                        about_tab = page.query_selector("//button[contains(@aria-label, 'About')]")
                        if about_tab:
                            print("Opening the tab...")
                            about_tab.click()
                            time.sleep(0.5)  # Memastikan konten telah dimuat sepenuhnya

                            # Mengekstrak konten HTML baru dan parsing lagi
                            page_source = page.content()
                            tree = html.fromstring(page_source)

                            # Mengekstrak accessibility, amenities, dan children dari tab About
                            accessibility = tree.xpath('//h2[text()="Accessibility"]/following-sibling::ul//span[contains(@aria-label,"Has")]')
                            amenities = tree.xpath('//h2[text()="Amenities"]/following-sibling::ul//span[contains(@aria-label,"Has")]/text()')
                            children = tree.xpath('//h2[text()="Children"]/following-sibling::ul//span[contains(@aria-label,"Good")]')

                            # Membersihkan dan menyusun data tambahan
                            data_entry["Wheelchair-accessible"] = "true" if accessibility else "false"
                            data_entry["Amenities"] = amenities[0].strip()  if amenities else None
                            data_entry["Good for children"] = "true" if children else "false"

                        else:
                            print("About tab not found. Skipping additional data extraction.")

                    except Exception as e:
                        print(f"Error during button clicking or data extraction: {e}")

                    time.sleep(0.5)

                    # Kembali ke bagian sebelumnya
                    try:
                        back_button = page.query_selector('//button[@aria-label="Back"]')
                        if back_button:
                            back_button.click()
                    except Exception as e:
                        print(f"Error during button clicking or data extraction: {e}")
                    
                    time.sleep(1)

                    print(f"Extracted data: {data_entry}")

                    # Menambahkan ke daftar data yang diekstraksi
                    extracted_data.append(data_entry)

                    # Kembali ke bagian sebelumnya
                    try:
                        back_button = page.query_selector('//button[@aria-label="Back"]')
                        if back_button:
                            back_button.click()
                    except Exception as e:
                        print(f"Error during button clicking or data extraction: {e}")
                    
                    time.sleep(1)

                    # mengekstrak konten halaman
                    page_source = page.content()
                    tree = html.fromstring(page_source)

                # Jika sudah mencapai batas akhir
                end_list = page.query_selector('//span[contains(text(),"end of the list.")]')
                if end_list:
                    break    

        except Exception as e:
            print("Error during clicking or extracting data:", e)

        # Menutup browser
        browser.close()

    # Langkah 4: Simpan data yang diekstraksi ke file Excel
    if extracted_data:
        # Konversi data yang diekstraksi menjadi DataFrame
        data_df = pd.DataFrame(extracted_data)
        
        # Ubah kolom daftar menjadi string untuk membuatnya dapat di-hash
        if 'Amenities' in data_df.columns:
            data_df['Amenities'] = data_df['Amenities'].apply(lambda x: ', '.join(x) if isinstance(x, list) else x)

        if 'Images' in data_df.columns:
            data_df['Images'] = data_df['Images'].apply(lambda x: ', '.join(x) if isinstance(x, list) else x)


        file_path = "file_path_bla_bla.xlsx"

        # Simpan data gabungan ke dalam file
        data_df.to_excel(file_path, index=False)
        print(f"Data saved to '{file_path}'.")


# Langkah 5: Membaca kota dari Excel dan jalankan scraper untuk setiap kota
city_data = pd.read_excel('city_list.xlsx')

# Nama kota ada di kolom bernama 'City' dan kategori ada di kolom bernama 'Category'
city_list = city_data['City'].tolist()
category_list = city_data['Category'].tolist()

# Lakukan pengulangan melalui kota-kota dan kumpulkan data untuk setiap kota
for city_name in city_list:
    for category_name in category_list:
        # Membersihkan string nama kota dan kategori
        city_name = city_name.strip()
        category_name = category_name.strip()
        
        # Memulai scraping melalui nama kota dan kategori
        print(f"Scraping data for city: {city_name}, category: {category_name}...")
        scrape_google_maps(city_name, category_name)  # Memanggil fungsi scraping
        
    print(f"Finished scraping all categories for city: {city_name}. Moving to the next city...\n")

    
