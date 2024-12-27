import streamlit as st
import openai
import os
import datetime
import json

st.title("Application Document Generation")

st.markdown("""
**Instructions:**
1. You can select individual jobs or generate documents for all matches of a certain type.
2. Documents include:
   - A cover letter (based on a template and tailored to the job).
   - A tailored resume (based on a template and your original resume).
   - Step-by-step application instructions based on the job's application procedure.
3. After generating the tailored resume, the system will provide an explanation of what changed from your original resume.
4. If you select individual jobs, press "Generate Documents" after selection.
   If you press "Generate Docs for All Minimum Matches" or "Generate Docs for All Good Matches", generation will start immediately.
""")

openai.api_key = os.getenv("OPENAI_API_KEY")

if 'resume_matches' not in st.session_state or len(st.session_state.resume_matches) == 0:
    st.write("No resume matches found. Please run the resume matching page first.")
else:
    matches = st.session_state.resume_matches
    # Load templates
    cover_letter_template = ""
    resume_template = ""
    if os.path.exists("cover_letter_template.txt"):
        with open("cover_letter_template.txt", "r", encoding="utf-8") as f:
            cover_letter_template = f.read()
    else:
        st.error("cover_letter_template.txt not found.")
    if os.path.exists("resume_template.txt"):
        with open("resume_template.txt", "r", encoding="utf-8") as f:
            resume_template = f.read()
    else:
        st.error("resume_template.txt not found.")

    applicable_jobs = [m for m in matches if m['resume_match_level'] in ['minimum', 'good']]

    if not applicable_jobs:
        st.write("No applicable jobs found from your matches.")
    else:
        st.markdown("### Select Jobs to Generate Documents")
        selected_item_numbers = st.multiselect(
            "Select Jobs",
            [f"{m['item_number']} - {m['job_title']} ({m['resume_match_level']})" for m in applicable_jobs],
            key="select_jobs_for_docs"
        )

        comment_box = st.text_area("Add comments or notes for refinement (optional):", key="comment_box")

        # Ensure we have the last resume text
        if 'last_resume_text' not in st.session_state or not st.session_state.last_resume_text.strip():
            st.warning("You need to provide your original resume text before generating documents.")
            resume_input = st.text_area("Paste your resume text here:", key="resume_paste")
            if st.button("Store Resume Text", key="store_resume_button"):
                st.session_state.last_resume_text = resume_input
        else:
            resume_text = st.session_state.last_resume_text

            def generate_from_template(doc_type, job, resume_text, notes, template):
                # job details
                job_details = st.session_state.job_details[job['item_number']]
                job_title = job_details.get('job_title', '')
                agency = job_details.get('agency', '')
                # Some job details may not have agency explicitly stored; if not, get from filtered_jobs if needed
                if not agency:
                    # Attempt to find from filtered jobs
                    for j in st.session_state.filtered_jobs:
                        if j['item_number'] == job['item_number']:
                            agency = j.get('agency', '')
                            break

                relevant_experience = "the qualifications and experience mentioned in the candidate's resume"

                prompt = f"""
You are an expert career services writer. Using the provided template, tailor the {doc_type} specifically for this job.

Job Details:
Title: {job_title}
Agency: {agency}
Minimum Qualifications: {job_details.get('minimum_qualifications', '')}
Duties: {job_details.get('duties_description', '')}
Location: {job_details.get('location', '')}
Application Procedure: {job_details.get('application_procedure', '')}

Candidate's Original Resume:
{resume_text}

Notes from Candidate:
{notes}

Template:
{template}

Instructions:
- Incorporate the job title, agency, and relevant experience into the template.
- Maintain a professional, expert tone.
- For the resume, highlight the most relevant experience and skills based on the job requirements.
- Output ONLY the full {doc_type} text with no extra commentary.
"""
                completion = openai.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "system", "content": prompt}],
                    max_tokens=2000,
                    temperature=0.7
                )
                return completion.choices[0].message.content.strip()

            def generate_application_instructions(job, notes):
                job_details = st.session_state.job_details[job['item_number']]
                application_procedure = job_details.get('application_procedure', '')

                prompt = f"""
You are an expert career coach. Provide a clear, step-by-step set of instructions for the candidate to apply to this job based on the following application procedure. Be concise, but thorough. If the instructions involve emailing a resume and cover letter, specify subject lines and formats. If a weblink is involved, specify how to navigate there and what to fill out. If forms need to be completed, mention them.

Application Procedure:
{application_procedure}

Notes from Candidate:
{notes}

Respond with a numbered list of steps that the candidate should follow to apply.
"""
                completion = openai.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "system", "content": prompt}],
                    max_tokens=1000,
                    temperature=0.0
                )
                return completion.choices[0].message.content.strip()

            def explain_resume_changes(original_resume, tailored_resume):
                prompt = f"""
You are a professional editor. You have the candidate's original resume and a newly tailored version. Explain in a short paragraph what changes and additions were made in the tailored resume compared to the original, focusing on how it was customized for the specific job.

Original Resume:
{original_resume}

Tailored Resume:
{tailored_resume}
"""
                completion = openai.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "system", "content": prompt}],
                    max_tokens=500,
                    temperature=0.0
                )
                return completion.choices[0].message.content.strip()

            def generate_docs_for_jobs(selected_jobs):
                if not selected_jobs:
                    st.warning("No jobs selected for document generation.")
                    return
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                output_dir = "generated_documents"
                os.makedirs(output_dir, exist_ok=True)

                for selected_job_str in selected_jobs:
                    parts = selected_job_str.split(" - ")
                    item_id = parts[0].strip()
                    job_obj = [m for m in matches if m['item_number'] == item_id][0]

                    # Generate cover letter
                    cover_letter = generate_from_template("cover letter", job_obj, resume_text, comment_box, cover_letter_template)
                    cl_path = os.path.join(output_dir, f"{item_id}_cover_letter_{timestamp}.txt")
                    with open(cl_path, "w", encoding="utf-8") as f:
                        f.write(cover_letter)

                    # Generate tailored resume
                    tailored_resume = generate_from_template("resume", job_obj, resume_text, comment_box, resume_template)
                    tr_path = os.path.join(output_dir, f"{item_id}_resume_{timestamp}.txt")
                    with open(tr_path, "w", encoding="utf-8") as f:
                        f.write(tailored_resume)

                    # Generate explanation of resume changes
                    changes_explanation = explain_resume_changes(resume_text, tailored_resume)

                    # Generate application instructions
                    instructions = generate_application_instructions(job_obj, comment_box)
                    ai_path = os.path.join(output_dir, f"{item_id}_instructions_{timestamp}.txt")
                    with open(ai_path, "w", encoding="utf-8") as f:
                        f.write(instructions)

                    st.success(f"Documents generated for job {item_id}!")
                    st.markdown("**Cover Letter:**")
                    st.text(cover_letter)
                    st.markdown("**Tailored Resume:**")
                    st.text(tailored_resume)
                    st.markdown("**Explanation of Resume Changes:**")
                    st.text(changes_explanation)
                    st.markdown("**Application Instructions:**")
                    st.text(instructions)

                st.write("Check the 'generated_documents' folder for the output files.")

            col1, col2, col3 = st.columns([1,1,1])

            with col1:
                if st.button("Generate Docs for All Minimum Matches"):
                    min_matches = [f"{m['item_number']} - {m['job_title']} ({m['resume_match_level']})" 
                                   for m in matches if m['resume_match_level'] == 'minimum']
                    generate_docs_for_jobs(min_matches)

            with col2:
                if st.button("Generate Docs for All Good Matches"):
                    good_matches = [f"{m['item_number']} - {m['job_title']} ({m['resume_match_level']})"
                                    for m in matches if m['resume_match_level'] == 'good']
                    generate_docs_for_jobs(good_matches)

            with col3:
                if st.button("Generate Documents", key="generate_docs_button"):
                    generate_docs_for_jobs(selected_item_numbers)
