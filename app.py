
from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename
from docx import Document
from collections import Counter
from datetime import datetime
import fitz
import sqlite3
import json
import os
import re
import io

app = Flask(__name__)
app.secret_key = "skillmatch_secret_key"

DATABASE = "skillmatch.db"
UPLOAD_FOLDER = "uploads"
MAX_FILE_SIZE = 10 * 1024 * 1024

app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

SKILLS = [
    "Python", "Java", "C++", "C", "HTML", "CSS",
    "JavaScript", "Flask", "Django", "SQL", "SQLite",
    "MySQL", "PostgreSQL", "MongoDB", "React",
    "Node.js", "PHP", "Git", "GitHub", "Linux",
    "Excel", "Power BI", "Tableau", "Machine Learning",
    "Data Analysis", "Pandas", "NumPy", "AWS", "Azure",
    "Docker", "REST API", "Communication", "Problem Solving"
]

RESUME_SECTIONS = [
    "education",
    "experience",
    "skills",
    "projects",
    "certifications"
]


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            resume_skills TEXT NOT NULL,
            required_skills TEXT NOT NULL,
            matched_skills TEXT NOT NULL,
            missing_skills TEXT NOT NULL,
            match_score INTEGER,
            created_at TEXT NOT NULL,
            resume_text TEXT
        )
    """)

    # Add resume_text when upgrading an older database
    columns = [
        row["name"]
        for row in conn.execute("PRAGMA table_info(analyses)").fetchall()
    ]

    if "resume_text" not in columns:
        conn.execute("ALTER TABLE analyses ADD COLUMN resume_text TEXT")

    conn.commit()
    conn.close()
init_db()


def extract_text(file):
    filename = secure_filename(file.filename)
    extension = filename.rsplit(".", 1)[-1].lower()

    if extension == "pdf":
        document = fitz.open(stream=file.read(), filetype="pdf")
        text = "\n".join(page.get_text() for page in document)
        document.close()
        return text

    if extension == "docx":
        document = Document(io.BytesIO(file.read()))
        return "\n".join(p.text for p in document.paragraphs)

    raise ValueError("Only PDF and DOCX files are supported.")


def find_skills(text):
    found = []

    for skill in SKILLS:
        pattern = r"(?<!\w)" + re.escape(skill) + r"(?!\w)"

        if re.search(pattern, text, re.IGNORECASE):
            found.append(skill)

    return found


def get_suggestions(resume_text, resume_skills, required_skills, missing_skills):
    text = resume_text.lower()

    section_tips = {
        "education": "Add an Education section with your qualification, institution and year.",
        "experience": "Add an Experience section. Include internships, training or practical work.",
        "skills": "Add a Skills section listing your technical and soft skills.",
        "projects": "Add a Projects section describing your projects, technologies and contributions.",
        "certifications": "Add a Certifications section for relevant courses and certificates."
    }

    missing_sections = [
        section for section in RESUME_SECTIONS
        if section not in text
    ]

    improvement_tips = []

    if missing_skills:
        improvement_tips.append(
            "Focus on learning these job-required skills: "
            + ", ".join(missing_skills)
        )

    if not any(word in text for word in ["summary", "objective", "profile"]):
        improvement_tips.append(
            "Add a professional summary or career objective at the beginning."
        )

    if not any(word in text for word in ["contact", "email", "phone"]):
        improvement_tips.append(
            "Make sure your contact information is clearly visible."
        )

    if len(resume_text.split()) < 100:
        improvement_tips.append(
            "Your resume appears short. Add relevant details about your projects, skills and achievements."
        )

    if not improvement_tips:
        improvement_tips.append(
            "Continue improving your resume by adding measurable achievements and relevant project details."
        )

    section_suggestions = [
        section_tips[section]
        for section in missing_sections
    ]

    if not section_suggestions:
        section_suggestions.append(
            "Your resume includes the main sections checked by SkillMatch. Keep them updated."
        )

    return improvement_tips, section_suggestions, missing_sections


def save_analysis(filename, resume_text, resume_skills,
                  required_skills, matched_skills, missing_skills, score):

    conn = get_db()

    conn.execute("""
        INSERT INTO analyses
        (filename, resume_skills, required_skills,
         matched_skills, missing_skills, match_score,
         created_at, resume_text)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        filename,
        json.dumps(resume_skills),
        json.dumps(required_skills),
        json.dumps(matched_skills),
        json.dumps(missing_skills),
        score,
        datetime.now().strftime("%d-%m-%Y %I:%M %p"),
        resume_text
    ))

    conn.commit()
    conn.close()


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    file = request.files.get("resume")
    job_description = request.form.get("job_description", "").strip()

    if not file or not file.filename:
        flash("Please upload your resume.")
        return redirect(url_for("home"))

    if not job_description:
        flash("Please enter a job description.")
        return redirect(url_for("home"))

    if "." not in file.filename:
        flash("Invalid file.")
        return redirect(url_for("home"))

    extension = file.filename.rsplit(".", 1)[-1].lower()

    if extension not in ["pdf", "docx"]:
        flash("Only PDF and DOCX files are supported.")
        return redirect(url_for("home"))

    try:
        resume_text = extract_text(file)

        if not resume_text.strip():
            flash("Could not extract text from this resume.")
            return redirect(url_for("home"))

        resume_skills = find_skills(resume_text)
        required_skills = find_skills(job_description)

        matched_skills = [
            skill for skill in required_skills
            if skill in resume_skills
        ]

        missing_skills = [
            skill for skill in required_skills
            if skill not in resume_skills
        ]

        if required_skills:
            score = round(
                len(matched_skills) / len(required_skills) * 100
            )
        else:
            score = None

        improvement_tips, section_suggestions, missing_sections = (
            get_suggestions(
                resume_text,
                resume_skills,
                required_skills,
                missing_skills
            )
        )

        filename = secure_filename(file.filename)

        save_analysis(
            filename,
            resume_text,
            resume_skills,
            required_skills,
            matched_skills,
            missing_skills,
            score
        )

        return render_template(
            "result.html",
            filename=filename,
            resume_skills=resume_skills,
            required_skills=required_skills,
            matched_skills=matched_skills,
            missing_skills=missing_skills,
            score=score,
            improvement_tips=improvement_tips,
            section_suggestions=section_suggestions,
            missing_sections=missing_sections
        )

    except Exception as error:
        app.logger.exception("Resume analysis failed")
        flash("Unable to analyze this file. Please check that it is a valid PDF or DOCX.")
        return redirect(url_for("home"))


@app.route("/history")
def history():
    conn = get_db()
    analyses = conn.execute(
        "SELECT * FROM analyses ORDER BY id DESC"
    ).fetchall()
    conn.close()

    return render_template("history.html", analyses=analyses)


@app.route("/history/<int:analysis_id>")
def view_analysis(analysis_id):
    conn = get_db()
    analysis = conn.execute(
        "SELECT * FROM analyses WHERE id = ?",
        (analysis_id,)
    ).fetchone()
    conn.close()

    if not analysis:
        flash("Analysis not found.")
        return redirect(url_for("history"))

    data = dict(analysis)

    data["resume_skills"] = json.loads(data["resume_skills"])
    data["required_skills"] = json.loads(data["required_skills"])
    data["matched_skills"] = json.loads(data["matched_skills"])
    data["missing_skills"] = json.loads(data["missing_skills"])

    resume_text = data.get("resume_text") or ""

    improvement_tips, section_suggestions, missing_sections = (
        get_suggestions(
            resume_text,
            data["resume_skills"],
            data["required_skills"],
            data["missing_skills"]
        )
    )

    return render_template(
        "view.html",
        analysis=data,
        improvement_tips=improvement_tips,
        section_suggestions=section_suggestions,
        missing_sections=missing_sections
    )


@app.route("/dashboard")
def dashboard():
    conn = get_db()

    analyses = conn.execute(
        "SELECT * FROM analyses ORDER BY id DESC"
    ).fetchall()

    conn.close()

    scores = [
        row["match_score"]
        for row in analyses
        if row["match_score"] is not None
    ]

    average_score = round(sum(scores) / len(scores)) if scores else 0
    highest_score = max(scores) if scores else 0

    skill_counter = Counter()

    for row in analyses:
        skill_counter.update(json.loads(row["resume_skills"]))

    top_skills = skill_counter.most_common(8)

    score_ranges = {
        "0-20%": 0,
        "21-40%": 0,
        "41-60%": 0,
        "61-80%": 0,
        "81-100%": 0
    }

    for score in scores:
        if score <= 20:
            score_ranges["0-20%"] += 1
        elif score <= 40:
            score_ranges["21-40%"] += 1
        elif score <= 60:
            score_ranges["41-60%"] += 1
        elif score <= 80:
            score_ranges["61-80%"] += 1
        else:
            score_ranges["81-100%"] += 1

    return render_template(
        "dashboard.html",
        total=len(analyses),
        average_score=average_score,
        highest_score=highest_score,
        top_skills=top_skills,
        all_analyses=analyses,
        score_labels=list(score_ranges.keys()),
        score_values=list(score_ranges.values()),
        skill_labels=[item[0] for item in top_skills],
        skill_values=[item[1] for item in top_skills]
    )


@app.errorhandler(413)
def file_too_large(error):
    flash("File is too large. Maximum upload size is 10 MB.")
    return redirect(url_for("home"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
