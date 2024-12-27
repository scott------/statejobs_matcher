import streamlit as st
import openai
import json
import datetime
import PyPDF2
import os

st.title("Resume Matching")

st.markdown("""
**Instructions:**
1. Ensure you have scraped job details on the main page first.
2. Upload your resume (PDF or TXT).
3. The system will:
   - Infer your professional domain and approximate salary range from your resume.
   - Use this information to determine if each job is a good match, minimum match, or no match.
4. Good matches are jobs that:
   - Match your domain (e.g., healthcare for a nurse, IT for a data engineer).
   - Offer a salary range close to your inferred current salary range.
   - Meet the minimum qualifications.
""")

openai.api_key = os.getenv("OPENAI_API_KEY")

if 'job_details' not in st.session_state or not st.session_state.job_details:
    st.write("No job details available. Please return to the main page and scrape data first.")
else:
    resume_file = st.file_uploader("Upload your resume (PDF or TXT):", type=['pdf', 'txt'], key="resume_upload")
    if resume_file is not None:
        filetype = resume_file.name.split('.')[-1].lower()
        resume_text = ""
        if filetype == 'pdf':
            pdf_reader = PyPDF2.PdfReader(resume_file)
            for page in pdf_reader.pages:
                resume_text += page.extract_text() + "\n"
        else:
            resume_text = resume_file.read().decode('utf-8', errors='ignore')

        st.session_state.last_resume_text = resume_text

        # Step 1: Infer candidate's domain and salary range from resume
        if st.button("Analyze Resume for Domain & Salary", key="analyze_resume_button"):
            analysis_prompt = f"""
You are an expert career advisor. Analyze the candidate's resume below and infer the candidate's professional domain (e.g. "Nursing", "Data Engineering", "Accounting", "Teaching", etc.) and provide a reasonable current salary range based on their experience and role indicated in the resume. Be practical and consider typical salaries for the given role and experience level.

Resume:
{resume_text}

Respond in JSON with the following format:
{{
  "candidate_domain": "string describing domain",
  "candidate_salary_range": "string describing approximate current salary range, e.g. '$70,000-$90,000'"
}}
"""
            try:
                completion = openai.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "system", "content": analysis_prompt}],
                    max_tokens=300,
                    temperature=0.0
                )
                response = completion.choices[0].message.content.strip()
                parsed = json.loads(response)
                st.session_state.candidate_domain = parsed.get("candidate_domain", "")
                st.session_state.candidate_salary_range = parsed.get("candidate_salary_range", "")
                st.success("Domain and salary range inferred successfully!")
                st.write("**Candidate Domain:**", st.session_state.candidate_domain)
                st.write("**Candidate Salary Range:**", st.session_state.candidate_salary_range)
            except Exception as e:
                st.error(f"Error inferring domain and salary range: {e}")

        # Step 2: Run Matching
        if 'candidate_domain' in st.session_state and 'candidate_salary_range' in st.session_state and st.session_state.candidate_domain and st.session_state.candidate_salary_range:
            if st.button("Run Matching", key="run_matching_button"):
                details = st.session_state.job_details
                jobs = list(details.values())
                total = len(jobs)
                results = []

                progress_bar = st.progress(0)
                status_text = st.empty()

                # Add instructions on how to determine good/minimum/no match
                # Good match: meets min qual, domain aligns, salary close
                # Minimum: meets min qual but not domain or salary not aligned
                # No match: does not meet min qual

                for i, job in enumerate(jobs):
                    progress_bar.progress(int((i+1)/total*100))
                    status_text.text(f"Processing job {i+1} of {total}...")

                    if 'error' in job:
                        results.append({
                            "item_number": job['item_number'],
                            "job_title": job.get('job_title', ''),
                            "resume_match_level": "no match",
                            "match_explanation": "Job details could not be retrieved."
                        })
                        continue

                    min_qual = job.get("minimum_qualifications", "").strip()
                    if not min_qual:
                        results.append({
                            "item_number": job['item_number'],
                            "job_title": job.get('job_title', ''),
                            "resume_match_level": "no match",
                            "match_explanation": "No minimum qualifications listed."
                        })
                        continue

                    job_title = job.get('job_title', '')
                    salary_range = job.get('salary_range', '')  # might be something like "$42,939 to $52,989 Annually"
                    # We'll rely on the LLM to interpret salary_range and domain alignment.
                    # Additional domain cues might come from 'agency' or 'duties_description'.

                    matching_prompt = f"""
You are a professional career advisor. Classify the match of this candidate to the following job:

Candidate Domain: {st.session_state.candidate_domain}
Candidate Current Salary Range: {st.session_state.candidate_salary_range}

Job Details:
Title: {job_title}
Salary Range: {salary_range}
Minimum Qualifications: {min_qual}
Duties: {job.get('duties_description', '')}
Agency: {job.get('agency', '')}

The candidate's resume:
{resume_text}

Criteria:
- The candidate must meet the minimum qualifications for the job to be at least "minimum".
- The candidate's domain should align with the job's domain to be considered "good".
- The job’s salary range should be reasonably close to the candidate’s current salary range for a "good" match.
- If the candidate meets minimum qualifications but domain or salary are not well aligned, then "minimum".
- If the candidate does not meet minimum qualifications, then "no match".
- If the candidate meets minimum qualifications and both domain alignment and salary proximity are good, then "good".

DO NOT include triple backticks or code fences. Only return a pure JSON object. 
Your response MUST be a valid JSON object and must have the following structure:
{{
  "resume_match_level": "minimum" | "good" | "no match",
  "match_explanation": "A brief explanation here."
}}
"""
                    try:
                        completion = openai.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[{"role": "system", "content": matching_prompt}],
                            max_tokens=300,
                            temperature=0.0
                        )
                        response = completion.choices[0].message.content.strip()
                        try:
                            parsed = json.loads(response)
                            match_level = parsed.get("resume_match_level", "no match").lower()
                            explanation = parsed.get("match_explanation", "")
                        except json.JSONDecodeError:
                            match_level = "no match"
                            explanation = f"Error during evaluation: Unable to parse JSON. Raw response: {response}"
                    except Exception as e:
                        match_level = "no match"
                        explanation = f"Error during evaluation: {e}"

                    results.append({
                        "item_number": job['item_number'],
                        "job_title": job_title,
                        "resume_match_level": match_level,
                        "match_explanation": explanation
                    })

                st.session_state.resume_matches = results
                st.success("Resume matching completed!")

                # Display results
                for r in results:
                    st.write(f"**{r['job_title']}** (Item {r['item_number']}): {r['resume_match_level'].title()}")
                    st.write(r['match_explanation'])
                    if r['item_number'] in st.session_state.job_details:
                        with st.expander("View Job Details"):
                            st.json(st.session_state.job_details[r['item_number']])

                if st.button("Save Resume Match Results", key="save_results_button"):
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    results_path = f"resume_matches_{timestamp}.json"
                    with open(results_path, "w", encoding="utf-8") as f:
                        json.dump(results, f, ensure_ascii=False, indent=2)
                    st.success(f"Saved resume match results to {results_path}")
        else:
            st.info("Please analyze your resume first for domain and salary before running matching.")
