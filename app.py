import streamlit as st
import pandas as pd
import json
from groq import Groq
import os
import re
import matplotlib.pyplot as plt

# Load datasets
@st.cache_data
def load_data():
    enrollment_df = pd.read_excel("enrollment_with_electives_final.xlsx")
    term_history_df = pd.read_excel("term_sorted_final.xlsx")
    elective_schedule_df = pd.read_excel("elective_schedule_final.xlsx")
    return enrollment_df, term_history_df, elective_schedule_df

enrollment_df, term_history_df, elective_schedule_df = load_data()

# Initialize Groq client
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Find student in database
def find_student(query):
    # Extract name from query
    name_pattern = re.search(r'(?:I am|I\'m|My name is) ([A-Za-z ]+)', query)
    extracted_name = name_pattern.group(1).strip() if name_pattern else None
    
    # Try exact or partial match
    if extracted_name:
        matches = enrollment_df[enrollment_df["NAME_DISPLAY"].str.lower().str.contains(extracted_name.lower())]
        if not matches.empty:
            return matches.iloc[0]
    
    # Try any words in query
    for word in query.lower().split():
        if len(word) > 3:
            matches = enrollment_df[enrollment_df["NAME_DISPLAY"].str.lower().str.contains(word)]
            if not matches.empty:
                return matches.iloc[0]
    
    return None

# Calculate academic strengths from grades using term_history data
# Calculate academic strengths from grades using term_history data
def get_academic_strengths(student_id):
    # Get student's course data from enrollment
    student_courses = enrollment_df[enrollment_df["EMPLID"] == student_id].to_dict(orient="records")
    
    # Get GPA from term history data
    student_terms = term_history_df[term_history_df["EMPLID"] == student_id]
    
    # Get latest valid GPA as the actual cumulative GPA
    latest_valid_gpa = 0.0
    if not student_terms.empty:
        # Filter for valid term GPAs
        valid_terms = student_terms[student_terms["TERM_GPA"] > 0].sort_values("STRM", ascending=True)
        if not valid_terms.empty:
            latest_valid_gpa = valid_terms["TERM_GPA"].iloc[-1] 
    
    # Default to enrollment data if no valid GPA found
    if latest_valid_gpa == 0 and student_courses and "CUM_GPA" in student_courses[0]:
        try:
            latest_valid_gpa = float(student_courses[0]["CUM_GPA"])
        except (ValueError, TypeError):
            latest_valid_gpa = 0.0
    
    # Updated grade values - removed A+, A-, B-, C-, D-
    grade_values = {'A': 4.0, 'B+': 3.3, 'B': 3.0, 'C+': 2.3, 'C': 2.0, 
                    'D+': 1.3, 'D': 1.0, 'F': 0.0, 'S': 3.0, 'U': 0.0}
    
    subjects = {}
    for course in student_courses:
        subject = course.get("SUBJECT")
        grade = course.get("CRSE_GRADE_OFF")
        
        if not subject or not grade or grade not in grade_values:
            continue
            
        if subject not in subjects:
            subjects[subject] = {"total": 0, "count": 0, "grades": []}
        
        subjects[subject]["total"] += grade_values[grade]
        subjects[subject]["count"] += 1
        subjects[subject]["grades"].append(grade)
    
    # Calculate average and sort
    strengths = {}
    for subject, data in subjects.items():
        if data["count"] > 0:
            strengths[subject] = {
                "average": round(data["total"] / data["count"], 2),
                "count": data["count"],
                "grades": data["grades"]
            }
    
    return dict(sorted(strengths.items(), key=lambda x: x[1]["average"], reverse=True)), latest_valid_gpa


# Get completed courses
def get_completed_courses(student_data):
    completed = []
    
    # Extract from Elective_Courses_finished
    for record in student_data:
        if "Elective_Courses_finished" in record and record["Elective_Courses_finished"]:
            try:
                if isinstance(record["Elective_Courses_finished"], list):
                    completed.extend(record["Elective_Courses_finished"])
                else:
                    # Try parsing as string representation of list
                    course_list = eval(record["Elective_Courses_finished"])
                    if isinstance(course_list, list):
                        completed.extend(course_list)
            except:
                pass
    
    # Add courses with passing grades
    for course in student_data:
        if course.get("CRSE_GRADE_OFF") not in ["F", "W", "I", "U", "WA"]:
            if "CRSE_ID" in course:
                completed.append(str(course["CRSE_ID"]))
    
    return list(set(completed))

# Plot GPA trend
def plot_gpa_trend(student_id):
    student_terms = term_history_df[term_history_df["EMPLID"] == student_id]
    if student_terms.empty:
        return None
    
    # Filter valid terms with GPA values and sort
    valid_terms = student_terms[student_terms["TERM_GPA"] > 0].sort_values("STRM")
    
    if len(valid_terms) < 2:
        return None
    
    # Create plot
    fig, ax = plt.subplots(figsize=(8, 3))
    terms = valid_terms["STRM"].astype(str)
    gpas = valid_terms["TERM_GPA"]
    
    ax.plot(terms, gpas, marker='o', linestyle='-', color='#1f77b4')
    ax.set_xlabel("Term")
    ax.set_ylabel("GPA")
    ax.set_title("Term GPA Trend")
    ax.grid(True, linestyle='--', alpha=0.7)
    ax.set_ylim(0, 4)
    
    # Add average line
    avg_gpa = gpas.mean()
    ax.axhline(y=avg_gpa, color='r', linestyle='--', alpha=0.7, label=f'Avg: {avg_gpa:.2f}')
    ax.legend()
    
    # Rotate x labels for better readability
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    return fig, avg_gpa

# Get GPA trend analysis
def analyze_gpa_trend(student_id):
    student_terms = term_history_df[term_history_df["EMPLID"] == student_id]
    if student_terms.empty:
        return "No GPA data available", 0
    
    # Filter valid terms with GPA values and sort
    valid_terms = student_terms[student_terms["TERM_GPA"] > 0].sort_values("STRM")
    
    if len(valid_terms) < 2:
        return "Insufficient term data for trend analysis", valid_terms["TERM_GPA"].iloc[0] if not valid_terms.empty else 0
    
    # Calculate trend
    gpas = valid_terms["TERM_GPA"].tolist()
    latest_gpa = gpas[-1]
    previous_gpa = gpas[-2]
    avg_gpa = sum(gpas) / len(gpas)
    
    if latest_gpa > previous_gpa + 0.2:
        trend = "improving"
    elif latest_gpa < previous_gpa - 0.2:
        trend = "declining"
    else:
        trend = "stable"
    
    return trend, avg_gpa

# Recommend electives based on strengths and actual GPA
def recommend_electives(student_strengths, completed_courses, available_electives, actual_gpa):
    recommendations = []
    
    # Define difficulty tiers based on GPA
    if actual_gpa >= 3.5:
        difficulty_tier = "high"
    elif actual_gpa >= 2.5:
        difficulty_tier = "medium"
    else:
        difficulty_tier = "low"
    
    for elective in available_electives:
        course_id = str(elective.get("course_id", ""))
        subject = elective.get("subject", "")
        
        # Skip completed courses
        if course_id in completed_courses:
            continue
        
        # Score calculation
        score = 0
        
        # Match with academic strengths
        if subject in student_strengths:
            score += student_strengths[subject]["average"] * 2
        
        # Adjust based on actual GPA
        course_difficulty = elective.get("difficulty", "medium")
        
        # Match course difficulty with student's GPA tier
        if difficulty_tier == "low" and course_difficulty == "high":
            score -= 2  # Penalize high difficulty courses for low GPA students
        elif difficulty_tier == "high" and course_difficulty == "low":
            score -= 0.5  # Slightly reduce score for high GPA students and low difficulty courses
        elif difficulty_tier == course_difficulty:
            score += 1  # Bonus for matching difficulty level
        
        # Check scheduling and capacity
        capacity_issue = elective.get("Capacity_Issue", "") != "OK"
        timing_issue = elective.get("Timing_Issue", "") != "OK"
        
        if capacity_issue:
            score -= 1
        if timing_issue:
            score -= 0.5
        
        recommendations.append({
            "course_id": course_id,
            "title": elective.get("course_title", ""),
            "subject": subject,
            "schedule": f"{elective.get('scheduled_days', '')} {elective.get('start_time', '')}-{elective.get('end_time', '')}",
            "instructor": elective.get("instructor", ""),
            "capacity_issue": capacity_issue,
            "timing_issue": timing_issue,
            "difficulty": course_difficulty,
            "score": score
        })
    
    # Sort by score and get top 5
    return sorted(recommendations, key=lambda x: x["score"], reverse=True)[:5]

# System prompt for LLM
system_prompt = """
You are an Academic Advisor Assistant for a Middle Eastern university. Provide personalized academic advice based on student data.

Focus on:
1. Addressing the student by name and referencing their academic standing
2. Analyzing their GPA trend (improving, declining, stable)
3. Identifying academic strengths and areas for growth
4. Recommending appropriate electives based on strengths and interests
5. Noting any scheduling constraints or capacity issues

Keep your response concise yet personalized, and provide clear rationales for each recommendation.
"""

# Streamlit UI
st.title("🎓 Student Advisory BOT")

query = st.text_input("Ask your academic advisor:", 
                     placeholder="e.g., I'm Yaman Ahmed Al saadi, what electives fit my profile?")

if query:
    with st.spinner("Analyzing academic records..."):
        # Find student
        student = find_student(query)
        
        if student is not None:
            student_id = student["EMPLID"]
            
            # Get student data
            student_enrollment = enrollment_df[enrollment_df["EMPLID"] == student_id].to_dict(orient="records")
            
            # Analysis - now using the corrected functions
            strengths, actual_cum_gpa = get_academic_strengths(student_id)
            completed_courses = get_completed_courses(student_enrollment)
            
            # Get GPA trend
            gpa_fig, avg_term_gpa = plot_gpa_trend(student_id)
            gpa_trend, _ = analyze_gpa_trend(student_id)
            
            # Recommend electives with actual GPA
            recommendations = recommend_electives(
                strengths, 
                completed_courses, 
                elective_schedule_df.to_dict(orient="records"),
                actual_cum_gpa
            )
            
            # Prepare context for LLM
            top_strengths = {k: v["average"] for k, v in list(strengths.items())[:3]}
            context = {
                "student": {
                    "name": student["NAME_DISPLAY"],
                    "id": student["EMPLID"],
                    "program": student.get("ACAD_PROG", ""),
                    "gpa": actual_cum_gpa,
                    "gpa_trend": gpa_trend
                },
                "strengths": top_strengths,
                "completed_courses": completed_courses[:5],
                "recommendations": recommendations
            }
            
            # User prompt
            user_prompt = f"""
            Student query: "{query}"
            
            Student: {context['student']['name']} (ID: {context['student']['id']})
            Academic Program: {context['student']['program']}
            GPA: {context['student']['gpa']} (Trend: {context['student']['gpa_trend']})
            
            Academic strengths: {json.dumps(top_strengths)}
            
            Top 5 recommended electives:
            {json.dumps(recommendations, indent=2)}
            
            Provide a brief, personalized academic advisory response addressing the student by name.
            Include 3-5 specific elective recommendations with clear rationales based on their strengths.
            Note any scheduling issues with the recommended courses.
            """
            
            # Call LLM
            try:
                response = client.chat.completions.create(
                    model="llama3-70b-8192",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.7,
                )
                
                # Main content
                st.markdown("### 📋 Advisor Recommendation")
                st.markdown(response.choices[0].message.content)
                
                # Show elective table
                st.subheader("Recommended Electives")
                if recommendations:
                    rec_df = pd.DataFrame([
                        {
                            "Course": f"{r['course_id']} - {r['title']}",
                            "Schedule": r["schedule"],
                            "Instructor": r["instructor"],
                            "Difficulty": r["difficulty"].capitalize(),
                            "Issues": ("⚠️ Capacity" if r["capacity_issue"] else "") + 
                                     (" | ⏰ Timing" if r["timing_issue"] else "")
                        } for r in recommendations
                    ])
                    st.dataframe(rec_df, use_container_width=True)
                
                # Sidebar with student info
                with st.sidebar:
                    st.subheader("Student Profile")
                    st.write(f"**Name:** {student['NAME_DISPLAY']}")
                    st.write(f"**ID:** {student['EMPLID']}")
                    st.write(f"**Program:** {student.get('ACAD_PROG', 'N/A')}")
                    st.write(f"**GPA:** {actual_cum_gpa}")
                    st.write(f"**GPA Trend:** {gpa_trend.capitalize()}")
                    
                    st.subheader("Academic Strengths")
                    for subject, data in list(strengths.items())[:3]:
                        st.write(f"**{subject}:** {data['average']} ({data['count']} courses)")
                    
                    if gpa_fig:
                        st.subheader("GPA Trend")
                        st.pyplot(gpa_fig)
                
            except Exception as e:
                st.error(f"Error: {str(e)}")
        else:
            st.warning("Student not found. Please check the name and try again.")