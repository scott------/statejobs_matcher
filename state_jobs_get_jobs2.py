import streamlit as st
import requests
from bs4 import BeautifulSoup
import json
import datetime
import re

st.set_page_config(page_title="Job Matching Application", page_icon="📝", layout="wide")

# Initialize session state
if 'jobs_data' not in st.session_state:
    st.session_state.jobs_data = []
if 'filtered_jobs' not in st.session_state:
    st.session_state.filtered_jobs = []
if 'job_details' not in st.session_state:
    st.session_state.job_details = {}
if 'resume_matches' not in st.session_state:
    st.session_state.resume_matches = []
if 'selected_jobs_for_docs' not in st.session_state:
    st.session_state.selected_jobs_for_docs = []

st.title("Job Scraping and Filtering")

st.markdown("""
**Instructions:**
1. Click "Scrape State Jobs" to fetch the latest vacancy table data from StateJobsNY.
2. Filter jobs by county.
3. Scrape detailed job information for filtered jobs.
4. Save filtered job data for downstream pages.
""")

VACANCY_URL = "https://statejobs.ny.gov/employees/vacancyTable.cfm?searchResults=Yes&Keywords=&title=&JurisClassID=&AgID=&isnyhelp=&minDate=&maxDate=&employmentType=&gradeCompareType=GT&grade=&SalMin="
def scrape_vacancy_table(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        content = response.text
        soup = BeautifulSoup(content, 'html.parser')
        rows = soup.select('table tbody tr')
        jobs = []
        for row in rows:
            cols = row.find_all('td')
            if len(cols) < 7:
                continue
            item_number = cols[0].get_text(strip=True)
            job_title = cols[1].get_text(strip=True)
            salary_grade = cols[2].get_text(strip=True)
            posting_date = cols[3].get_text(strip=True)
            application_deadline = cols[4].get_text(strip=True)
            agency = cols[5].get_text(strip=True)
            county = cols[6].get_text(strip=True)

            jobs.append({
                "item_number": item_number,
                "job_title": job_title,
                "salary_grade": salary_grade,
                "posting_date": posting_date,
                "application_deadline": application_deadline,
                "agency": agency,
                "county": county
            })

        return jobs
    except Exception as e:
        st.error(f"Error fetching the vacancy table: {e}")
        return []



def scrape_job_details(item_id):
    detail_url = f"https://statejobs.ny.gov/employees/vacancyDetailsPrint.cfm?id={item_id}"
    resp = requests.get(detail_url, timeout=10)
    resp.raise_for_status()
    detail_soup = BeautifulSoup(resp.text, 'html.parser')
    
    # Extract posting date, application deadline, vacancy ID
    posting_date = ""
    application_deadline = ""
    vacancy_id = item_id
    top_header = detail_soup.find('h2', text="Review Vacancy")
    if top_header:
        top_p = top_header.find_next('p')
        if top_p:
            text = top_p.get_text(" ", strip=True)
            date_posted_match = re.search(r"Date Posted:\s*(\d{1,2}/\d{1,2}/\d{2})", text)
            app_due_match = re.search(r"Applications Due:\s*(\d{1,2}/\d{1,2}/\d{2})", text)
            vacancy_id_match = re.search(r"Vacancy ID:\s*(\d+)", text)
            if date_posted_match:
                posting_date = date_posted_match.group(1)
            if app_due_match:
                application_deadline = app_due_match.group(1)
            if vacancy_id_match:
                vacancy_id = vacancy_id_match.group(1)

    # Initialize fields
    job_title = ""
    minimum_qualifications = ""
    preferred_qualifications = ""  # not present in this example
    duties_description = ""
    salary_range = ""
    location = ""
    application_procedure = ""
    contact_information = ""

    vacancy_details = detail_soup.find('div', id='vacancyDetails')
    fields_map = {}

    if vacancy_details:
        # Extract fields from all <p class="row">
        # These are scattered after various <h3> headings.
        # We'll just loop through all <p class="row"> inside #vacancyDetails.
        for p in vacancy_details.find_all('p', class_='row'):
            left = p.find('span', class_='leftCol')
            right = p.find('span', class_='rightCol')
            if left and right:
                key = left.get_text(strip=True)
                val = right.get_text(" ", strip=True)
                fields_map[key] = val

    # Known fields:
    job_title = fields_map.get("Title", "")
    duties_description = fields_map.get("Duties Description", "")
    minimum_qualifications = fields_map.get("Minimum Qualifications", "")
    salary_range = fields_map.get("Salary Range", "")

    # Location:
    street_address = fields_map.get("Street Address", "")
    city = fields_map.get("City", "")
    state = fields_map.get("State", "")
    zip_code = fields_map.get("Zip Code", "")
    location_pieces = [street_address, city, state, zip_code]
    location = ", ".join([p for p in location_pieces if p.strip()])

    # Application Procedure (Notes on Applying)
    application_procedure = fields_map.get("Notes on Applying", "")

    # Contact Information:
    contact_name = fields_map.get("Name", "")
    contact_phone = fields_map.get("Telephone", "")
    contact_fax = fields_map.get("Fax", "")
    contact_email = fields_map.get("Email Address", "")
    contact_street = fields_map.get("Street", "")
    # These City/State/Zip Code might conflict with main location fields if repeated under contact info.
    # But from the given structure, contact info reuses fields like "City", "State", "Zip Code".
    # We'll just trust that location was already captured and that these are under Contact as well.
    # To differentiate, we must note that Contact Info appears after "Contact Information" heading.
    # We'll re-parse after the "Contact Information" <h3> if needed.
    # For simplicity, use what we have:
    # In the given example, fields_map is global, so city/state/zip_code may refer to either section.
    # We'll trust that these fields after "Contact Information" heading override previous ones.
    # To refine, we can re-check the HTML:
    # The contact info includes a separate "Street", "City", "State", "Zip Code" after "h5 class='heading' Address"
    # Since we didn't differentiate sections, let's just combine all contact address info again:
    
    # Attempt to find fields after "Contact Information" heading to re-derive contact address:
    contact_info_section = vacancy_details.find('h3', text="Contact Information")
    contact_address = ""
    if contact_info_section:
        # After Contact Information h3, we have fields:
        # We'll find them again here specifically.
        address_map = {}
        nxt = contact_info_section.find_next_sibling()
        while nxt and (nxt.name != 'h3'):
            if nxt.name == 'p' and 'row' in nxt.get('class', []):
                l = nxt.find('span', class_='leftCol')
                r = nxt.find('span', class_='rightCol')
                if l and r:
                    address_map[l.get_text(strip=True)] = r.get_text(" ", strip=True)
            nxt = nxt.find_next_sibling()

        # Rebuild contact info with these fields
        contact_street = address_map.get("Street", contact_street)
        contact_city = address_map.get("City", "")
        contact_state = address_map.get("State", "")
        contact_zip = address_map.get("Zip Code", "")
        contact_addr_pieces = [contact_street, contact_city, contact_state, contact_zip]
        contact_address = ", ".join([p for p in contact_addr_pieces if p.strip()])

    contact_info_parts = []
    if contact_name:
        contact_info_parts.append(f"Name: {contact_name}")
    if contact_phone:
        contact_info_parts.append(f"Phone: {contact_phone}")
    if contact_fax:
        contact_info_parts.append(f"Fax: {contact_fax}")
    if contact_email:
        contact_info_parts.append(f"Email: {contact_email}")
    if contact_address:
        contact_info_parts.append(f"Address: {contact_address}")

    contact_information = "\n".join(contact_info_parts)

    return {
        "item_number": vacancy_id,
        "posting_date": posting_date,
        "application_deadline": application_deadline,
        "job_title": job_title,
        "minimum_qualifications": minimum_qualifications,
        "preferred_qualifications": preferred_qualifications,
        "duties_description": duties_description,
        "salary_range": salary_range,
        "location": location,
        "application_procedure": application_procedure,
        "contact_information": contact_information
    }

def filter_jobs_by_county(jobs, selected_counties):
    if selected_counties:
        return [job for job in jobs if job['county'] in selected_counties]
    return jobs



if st.button("Scrape State Jobs", key="scrape_button"):
    jobs = scrape_vacancy_table(VACANCY_URL)
    st.session_state.jobs_data = jobs
    if jobs:
        st.success(f"Scraped {len(jobs)} jobs successfully!")

if st.session_state.jobs_data:
    counties = sorted(list(set([job['county'] for job in st.session_state.jobs_data])))

    counties_filter = st.multiselect("Filter by County", options=counties, default=[], key="county_filter_main_page")
    filtered = filter_jobs_by_county(st.session_state.jobs_data, counties_filter)

    st.session_state.filtered_jobs = filtered

    st.write(f"Total Jobs: {len(st.session_state.jobs_data)}")
    st.write(f"Filtered Jobs: {len(filtered)}")

    st.dataframe(filtered)

    if st.button("Scrape Job Details", key="scrape_details_button"):
        detail_results = {}
        progress_bar = st.progress(0)
        total = len(filtered)
        for i, job in enumerate(filtered):
            progress_bar.progress(int((i+1)/total*100))
            item_id = job['item_number']
            try:
                detail_data = scrape_job_details(item_id)
                detail_results[item_id] = detail_data
            except Exception as e:
                detail_results[item_id] = {
                    "item_number": item_id,
                    "error": str(e)
                }

        st.session_state.job_details = detail_results
        st.success("Job details scraped successfully!")
def save_job_data(filtered_jobs, job_details):
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filtered_jobs_path = f"filtered_jobs_{timestamp}.json"
    details_path = f"job_details_{timestamp}.json"
    with open(filtered_jobs_path, "w", encoding="utf-8") as f:
        json.dump(filtered_jobs, f, ensure_ascii=False, indent=2)
    with open(details_path, "w", encoding="utf-8") as f:
        json.dump(job_details, f, ensure_ascii=False, indent=2)
    st.success(f"Saved filtered jobs to {filtered_jobs_path} and details to {details_path}")



    if st.button("Save Filtered Jobs and Details", key="save_button"):
        save_job_data(st.session_state.filtered_jobs, st.session_state.job_details)
