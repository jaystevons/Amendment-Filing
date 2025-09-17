import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
from datetime import datetime
import urllib.parse
import os

class StockTitanScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
    def login(self, email, password):
        """Login to Stock Titan"""
        print("Attempting to login...")
        
        # Get the login page first
        login_page = self.session.get('https://www.stocktitan.net')
        login_page.raise_for_status()
        
        # Parse login form to get any hidden fields or CSRF tokens
        soup = BeautifulSoup(login_page.text, 'html.parser')
        
        # Look for login form or modal
        login_form = soup.find('form') or soup.find('div', {'id': 'login'})
        
        # Try to find the actual login endpoint
        # This might be an AJAX endpoint, let's try common patterns
        login_data = {
            'email': email,  # Using email as primary field
            'password': password,
            'login': 'Login',
            'submit': 'Login'
        }
        
        # Try posting to common login endpoints
        login_endpoints = [
            'https://www.stocktitan.net/login',
            'https://www.stocktitan.net/auth/login',
            'https://www.stocktitan.net/user/login',
            'https://www.stocktitan.net/api/login'
        ]
        
        for endpoint in login_endpoints:
            try:
                response = self.session.post(endpoint, data=login_data)
                if response.status_code == 200:
                    # Check if login was successful by looking for indicators
                    if 'dashboard' in response.url.lower() or 'logout' in response.text.lower():
                        print(f"Login successful via {endpoint}")
                        return True
            except:
                continue
        
        # If direct POST doesn't work, try to find the actual login form
        print("Trying to find login form on main page...")
        
        # Look for login button or form action
        login_button = soup.find('a', string=re.compile('Login', re.I)) or soup.find('button', string=re.compile('Login', re.I))
        if login_button and login_button.get('href'):
            login_url = urllib.parse.urljoin('https://www.stocktitan.net', login_button['href'])
            print(f"Found login URL: {login_url}")
            
            login_response = self.session.get(login_url)
            login_soup = BeautifulSoup(login_response.text, 'html.parser')
            
            # Find the actual login form
            form = login_soup.find('form')
            if form:
                action = form.get('action', '/login')
                method = form.get('method', 'POST').upper()
                
                # Get all form fields
                form_data = {}
                for input_field in form.find_all(['input', 'select', 'textarea']):
                    name = input_field.get('name')
                    if name:
                        if input_field.get('type') == 'password':
                            form_data[name] = password
                        elif 'email' in name.lower():
                            form_data[name] = email
                        elif input_field.get('value'):
                            form_data[name] = input_field['value']
                
                # Submit the form
                submit_url = urllib.parse.urljoin('https://www.stocktitan.net', action)
                
                if method == 'POST':
                    final_response = self.session.post(submit_url, data=form_data)
                else:
                    final_response = self.session.get(submit_url, params=form_data)
                
                # Check if login was successful
                if 'logout' in final_response.text.lower() or final_response.url != submit_url:
                    print("Login successful!")
                    return True
        
        print("Login failed - please check credentials or site structure may have changed")
        return False
    
    def get_sec_filings(self):
        """Scrape SEC filings from the live page"""
        print("Fetching SEC filings...")
        
        response = self.session.get('https://www.stocktitan.net/sec-filings/live.html')
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        filings = []
        
        # Look for different possible table structures
        # Try to find the main data table
        tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            
            # Skip header row
            for row in rows[1:]:
                cells = row.find_all(['td', 'th'])
                
                if len(cells) >= 4:  # Ensure we have enough columns
                    filing_data = {}
                    
                    # Extract data from cells - adjust indices based on actual table structure
                    try:
                        # This is a template - you may need to adjust based on actual HTML structure
                        filing_data['Date'] = cells[0].get_text(strip=True)
                        filing_data['Time'] = cells[1].get_text(strip=True) if len(cells) > 1 else ''
                        filing_data['Symbol'] = cells[2].get_text(strip=True) if len(cells) > 2 else ''
                        filing_data['Form Type'] = cells[3].get_text(strip=True) if len(cells) > 3 else ''
                        filing_data['Company'] = cells[4].get_text(strip=True) if len(cells) > 4 else ''
                        filing_data['Title'] = cells[5].get_text(strip=True) if len(cells) > 5 else ''
                        
                        # Look for URL link
                        link = row.find('a')
                        filing_data['URL'] = link['href'] if link else ''
                        
                        # Filter for amendments (contains "/A")
                        if '/A' in filing_data['Form Type']:
                            # Try to get AI Summary if available
                            filing_data['AI Summary'] = self.get_ai_summary(filing_data['URL'])
                            filings.append(filing_data)
                            print(f"Found amendment: {filing_data['Form Type']} - {filing_data['Company']}")
                            
                    except Exception as e:
                        print(f"Error parsing row: {e}")
                        continue
        
        # If no table found, try other structures
        if not filings:
            print("No table found, trying alternative parsing methods...")
            
            # Look for divs or other containers that might hold the data
            filing_containers = soup.find_all('div', class_=re.compile('filing|row|item'))
            
            for container in filing_containers:
                text = container.get_text()
                if '/A' in text:  # Check if it's an amendment
                    # Try to extract data from text
                    filing_data = self.parse_filing_text(container)
                    if filing_data:
                        filings.append(filing_data)
        
        return filings
    
    def get_ai_summary(self, filing_url):
        """Get AI summary for a specific filing"""
        if not filing_url:
            return ''
        
        try:
            # Make URL absolute if it's relative
            if filing_url.startswith('/'):
                filing_url = 'https://www.stocktitan.net' + filing_url
            
            # Add delay to be respectful
            time.sleep(1)
            
            response = self.session.get(filing_url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for AI summary section
            summary_selectors = [
                'div[class*="ai-summary"]',
                'div[class*="summary"]',
                'div[id*="summary"]',
                'div[class*="ai"]',
                '.summary',
                '#ai-summary'
            ]
            
            for selector in summary_selectors:
                summary_element = soup.select_one(selector)
                if summary_element:
                    return summary_element.get_text(strip=True)
            
            return ''
            
        except Exception as e:
            print(f"Error getting AI summary for {filing_url}: {e}")
            return ''
    
    def parse_filing_text(self, container):
        """Parse filing data from text content"""
        text = container.get_text()
        
        # Use regex to extract common patterns
        # This is a fallback method and may need adjustment
        
        filing_data = {
            'Date': '',
            'Time': '',
            'Symbol': '',
            'Form Type': '',
            'Company': '',
            'Title': '',
            'URL': '',
            'AI Summary': ''
        }
        
        # Look for form type with /A
        form_match = re.search(r'\b(\w+/A)\b', text)
        if form_match:
            filing_data['Form Type'] = form_match.group(1)
        
        # Look for stock symbol pattern
        symbol_match = re.search(r'\b([A-Z]{1,5})\b', text)
        if symbol_match:
            filing_data['Symbol'] = symbol_match.group(1)
        
        # Look for URL
        link = container.find('a')
        if link:
            filing_data['URL'] = link.get('href', '')
        
        return filing_data if filing_data['Form Type'] else None
    
    def save_to_csv(self, filings, filename=None):
        """Save filings data to CSV"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"sec_amendments_{timestamp}.csv"
        
        df = pd.DataFrame(filings)
        df.to_csv(filename, index=False)
        print(f"Data saved to {filename}")
        print(f"Total amendments found: {len(filings)}")
        
        return filename

def main():
    scraper = StockTitanScraper()
    
    # Get credentials from environment variables or use defaults
    email = os.getenv('STOCKTITAN_EMAIL', 'your-email@domain.com')
    password = os.getenv('STOCKTITAN_PASSWORD', 'your-password')
    
    if email == 'your-email@domain.com' or password == 'your-password':
        print("Please set STOCKTITAN_EMAIL and STOCKTITAN_PASSWORD environment variables")
        print("Or create a .env file with your credentials")
        return
    
    # Login
    if scraper.login(email, password):
        # Get SEC filings
        filings = scraper.get_sec_filings()
        
        if filings:
            # Save to CSV
            filename = scraper.save_to_csv(filings)
            
            # Display sample of results
            print(f"\nSample of collected data:")
            df = pd.DataFrame(filings)
            print(df.head())
            
        else:
            print("No amendment filings found. The page structure may have changed.")
            print("Please check the target URL and verify the page layout.")
    
    else:
        print("Failed to login. Please check credentials.")

if __name__ == "__main__":
    main()
