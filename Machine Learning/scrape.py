from playwright.sync_api import sync_playwright
from lxml import html
import time
import pandas as pd  # For saving data to Excel
import re
import os

# Function to scrape Google Maps data for a specific city
def scrape_google_maps(city_name, category_name):
    # Initialize a list to store the extracted data
    extracted_data = []
    processed_urls = set()  # Track processed URLs

    with sync_playwright() as p:
        # Launch Edge browser
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(no_viewport=True)

        # Modify the URL dynamically for each city
        search_url = f"https://www.google.com/maps/search/destinasi+wisata+{category_name.lower()}+di+{city_name.lower()}"

        try:
            print(f"Attempting to navigate to {search_url}")
            page.goto(search_url, timeout=30000)  # Set timeout to 30 seconds
        except Exception as e:
            print(f"Timeout while loading {search_url}.", e)

        # Wait for the body to load
        page.wait_for_selector("body")
        time.sleep(5)

        # Step 1: Change the language to English (US)
        try:
            menu_button = page.query_selector("//button[@aria-label='Menu']")
            if menu_button:
                print("Opening the menu...")
                menu_button.click()
                time.sleep(2)

                language_button = page.query_selector('//button[@class="aAaxGf T2ozWe"]')
                if language_button:
                    print("Opening the language settings...")
                    language_button.click()
                    time.sleep(2)

                    english_option = page.query_selector('//a[contains(@href, "hl=en")]')
                    if english_option:
                        print("Selecting English...")
                        english_option.click()
                        time.sleep(5)
                    else:
                        print("English option not found. Skipping language change.")
                else:
                    print("Language button not found. Skipping language change.")
            else:
                print("Menu button not found. Skipping language change.")
        except Exception as e:
            print("Error during language change:", e)

        # Step 2: Zoom in the map
        try:
            zoom_button = page.query_selector("//div[@id='zoom']//button[@aria-label='Zoom in']")
            num_clicks = 9
            if zoom_button:
                print("Zooming in...")
                for i in range(num_clicks):
                    zoom_button.click()
                    print(f"Clicked {i + 1} out of {num_clicks}")
                    time.sleep(0.2)

        except Exception as e:
            print("No clickable button. Skip zooming the page...", e)

        # Step 3: Loop through clickable items and extract data
        try:
            while True:
                clickable_items = page.query_selector_all("//div[@role='feed']//a[@aria-label and starts-with(@href, 'https://www.google.com/maps')]")
                if not clickable_items:
                    print("No more clickable items found.")
                    break
                    
                for index, item in enumerate(clickable_items):
                    href = item.get_attribute("href")
                    if href in processed_urls:
                        # Skip already processed items
                        continue

                    print(f"Clicking item {index + 1}...")
                    item.click(click_count=2)
                    processed_urls.add(href)

                    # Wait for content to load
                    time.sleep(2)

                    see_more = page.query_selector_all('//div[@class="MyEned"]//button[@aria-label="See more"]')
                    for index, item in enumerate(see_more):

                        print(f"Clicking more {index + 1}...")
                        item.click()
                        time.sleep(0.5)
                        
                    # Wait for content to load
                    time.sleep(1)

                    # Function to clean review text 
                    def clean_review_text(review_list): 
                        if review_list: 
                            cleaned_reviews = [review.replace('\n', '').strip() 
                            for review in review_list] 
                            return ' '.join(cleaned_reviews) # Join cleaned reviews into a single string if needed 
                        return None

                    # Extract page content
                    page_source = page.content()
                    tree = html.fromstring(page_source)

                    # Extract coordinates from the URL
                    current_url = page.url
                    match = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", current_url)
                    if match:
                        latitude = float(match.group(1))
                        longitude = float(match.group(2))
                    else:
                        latitude = None
                        longitude = None

                    # Extract the desired data using safer queries
                    place = tree.xpath("//h1[@class='DUwDvf lfPIob']/text()")
                    overview = tree.xpath("//div[@class='y0K5Df']//div[contains(@class,'PYvSYb')]/text()")
                    address = tree.xpath("//button[@class='CsEnBe' and contains(@aria-label,'Address')]//div[contains(@class,'Io6YTe')]/text()")
                    price = tree.xpath("(//div[@class='drwWxc'])[1]/text()")
                    rating = tree.xpath("//div[contains(@class,'F7nice')]//span[contains(@aria-hidden,'true')]/text()")
                    review = tree.xpath("//span[contains(@class,'wiI7pd')]/text()")
                    review_count = tree.xpath('//span[contains(@aria-label, "reviews")]/text()')

                    # Safely handle empty lists and set defaults
                    place = place[0] if place else None
                    overview = overview[0] if overview else None
                    address = address[0] if address else None
                    rating = float(rating[0]) if rating else None
                    review = clean_review_text(review) if review else None
                    review_count = int(re.sub(r'\D', '', review_count[0])) if review_count else 0 # Extract digits and convert to int
                    
                    # Clean and convert price 
                    if price: 
                        price = price[0].replace('Rp', '').replace('.', '').replace(',', '.').strip() 
                        try: 
                            price = float(price) 
                        except ValueError: 
                                price = 0.0 # Default to 0.0 if conversion fails 
                    else: price = 0.0

                    # Clean and structure the extracted data
                    data_entry = {
                        "Place": place,
                        "Overview": overview,
                        "Category": category_name,
                        "Address": address,
                        "City": city_name,
                        "Price": price,
                        "Rating": rating,
                        "Review": review,
                        "Review_count": review_count,
                        "Latitude": latitude,
                        "Longitude": longitude,
                    }

                    # Navigate to the second tab (About) to extract additional data
                    try:
                        about_tab = page.query_selector("//button[contains(@aria-label, 'About')]")
                        if about_tab:
                            print("Opening the tab...")
                            about_tab.click()
                            time.sleep(1)  # Ensure the content has fully loaded

                            # Extract the new HTML content and parse it again
                            page_source = page.content()
                            tree = html.fromstring(page_source)

                            # Extract amenities, accessibility, and children from About tab
                            accessibility = tree.xpath('//h2[text()="Accessibility"]/following-sibling::ul//span[contains(@aria-label,"Has")]')
                            amenities = tree.xpath('//h2[text()="Amenities"]/following-sibling::ul//span[contains(@aria-label,"Has")]/text()')
                            children = tree.xpath('//h2[text()="Children"]/following-sibling::ul//span[contains(@aria-label,"Good")]')

                            # Clean and structure the additional data
                            data_entry["Wheelchair-accessible"] = "true" if accessibility else "false"
                            data_entry["Amenities"] = amenities if amenities else None
                            data_entry["Good for children"] = "true" if children else "false"

                        else:
                            print("About tab not found. Skipping additional data extraction.")

                    except Exception as e:
                        print(f"Error during button clicking or data extraction: {e}")

                    print(f"Extracted data: {data_entry}")

                    # Add to extracted data list
                    extracted_data.append(data_entry)

                    time.sleep(1)

                    # Scroll the feed to load more items 
                    page.evaluate("document.querySelector('div[role=feed]').scrollBy(0, 500)")
                    print("Scrolling...")

                # If reached end of list
                end_list = page.query_selector('//span[contains(text(),"end of the list.")]')
                if end_list:
                    break    

        except Exception as e:
            print("Error during clicking or extracting data:", e)

        # Clean up
        browser.close()

    # Step 4: Save the extracted data to an Excel file
    if extracted_data:
        # Convert the extracted data to a DataFrame
        new_data_df = pd.DataFrame(extracted_data)
        
        # Convert list columns to strings to make them hashable
        if 'Amenities' in new_data_df.columns:
            new_data_df['Amenities'] = new_data_df['Amenities'].apply(lambda x: ', '.join(x) if isinstance(x, list) else x)


        file_path = f"C:/Users/muvir/Documents/Bangkit 2024/Capstone Project/Web scraping/web_scraping_gmaps/Data/dataset_{city_name.lower()}_{category_name.lower()}.xlsx"

        # Check if the file already exists
        if os.path.exists(file_path):
            print(f"File '{file_path}' already exists. Appending new data...")
            existing_data_df = pd.read_excel(file_path)

            # Append the new data and remove duplicates
            combined_data_df = pd.concat([existing_data_df, new_data_df], ignore_index=True)
            combined_data_df = combined_data_df.drop_duplicates()
        else:
            print(f"File '{file_path}' does not exist. Creating a new file...")
            combined_data_df = new_data_df

        # Save the combined data to the file
        combined_data_df.to_excel(file_path, index=False)
        print(f"Data saved to '{file_path}'.")


# Step 5: Read cities from Excel and run the scraper for each city
city_data = pd.read_excel('city_list.xlsx')  # Replace with the correct file path

# City names are in a column named 'City' and categories are in column named 'Category'
city_list = city_data['City'].tolist()
category_list = city_data['Category'].tolist()

# Loop through the cities and scrape data for each
for city_name in city_list:
    for category_name in category_list:
        print(f"Scraping data for {city_name} and category {category_name}...")
        city_name = city_name.strip()  # Remove any leading/trailing spaces
        category_name = category_name.strip() # Remove any leading/trailing spaces
        scrape_google_maps(city_name, category_name)  # Pass the city_name as an argument
