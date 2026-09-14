import os
import json
import time
import pathlib
import shutil
import re
from typing import Dict, Any, Optional

# Ensure RenderCV dependencies work smoothly
from rendercv.schema.rendercv_model_builder import build_rendercv_dictionary_and_model
from rendercv.renderer.typst import generate_typst
from rendercv.renderer.pdf_png import generate_pdf

def sanitize_phone(phone_str: str) -> Optional[str]:
    """Sanitize phone number for RenderCV pydantic validation or return None if invalid."""
    if not phone_str or not phone_str.strip():
        return None
    cleaned = phone_str.strip()
    if not cleaned.startswith("+"):
        digits = re.sub(r"\D", "", cleaned)
        if len(digits) == 10:
            cleaned = f"+57 {digits[:3]} {digits[3:6]} {digits[6:]}"
        elif len(digits) >= 11:
            cleaned = f"+{digits}"
        elif len(digits) >= 7:
            cleaned = f"+1 {digits}"
        else:
            return None
    return cleaned

def clean_date_str(date_val: str, is_end_date: bool = False) -> str:
    """Clean date string to match RenderCV expected format (YYYY, YYYY-MM, or 'present')."""
    if not date_val:
        return "present" if is_end_date else "2020"
    cleaned = date_val.strip().lower()
    if is_end_date and cleaned in ["presente", "present", "actualidad", "actual", "actualmente", "hoy", "now"]:
        return "present"
    
    match = re.search(r"\b(19\d\d|20\d\d)(?:-(0[1-9]|1[0-2]))?\b", cleaned)
    if match:
        return match.group(0)
        
    return "present" if is_end_date else "2020"

def convert_llm_json_to_rendercv_dict(parsed_data: Dict[str, Any], theme: str = "sb2nov") -> Dict[str, Any]:
    """
    Transforms the LLM output structure into RenderCV valid schema.
    Applies localized section titles from `section_labels`.
    """
    name = parsed_data.get("name", "Candidate").strip() or "Candidate"
    email = parsed_data.get("email", "").strip()
    phone = sanitize_phone(parsed_data.get("phone", ""))
    
    cv_info: Dict[str, Any] = {
        "name": name,
    }
    if email:
        cv_info["email"] = email
    if phone:
        cv_info["phone"] = phone
        
    # Social networks & Links
    social_networks = []
    linkedin = parsed_data.get("linkedin", "").strip()
    github = parsed_data.get("github", "").strip()
    portfolio = parsed_data.get("portfolio", "").strip()
    
    if linkedin:
        username = linkedin.split("in/")[-1].strip("/") if "in/" in linkedin else linkedin.replace("https://", "").replace("www.linkedin.com/", "").strip("/")
        social_networks.append({"network": "LinkedIn", "username": username or linkedin})
    if github:
        username = github.split("/")[-1].strip() if "github.com/" in github else github.replace("https://", "").strip("/")
        social_networks.append({"network": "GitHub", "username": username or github})
        
    if social_networks:
        cv_info["social_networks"] = social_networks
    if portfolio and portfolio.startswith("http"):
        cv_info["website"] = portfolio

    # Labels for localization
    default_labels = {
        "summary": "Professional Summary",
        "education": "Education",
        "skills": "Skills",
        "experience": "Work Experience",
        "projects": "Projects",
        "achievements": "Achievements"
    }
    labels = {**default_labels, **parsed_data.get("section_labels", {})}
    
    sections: Dict[str, Any] = {}
    
    # 1. Summary
    summary_text = parsed_data.get("summary", "").strip()
    if summary_text:
        sections[labels["summary"]] = [summary_text]
        
    # 2. Experience
    exp_list = parsed_data.get("experience", [])
    if exp_list and isinstance(exp_list, list):
        exp_entries = []
        for item in exp_list:
            if not isinstance(item, dict):
                continue
            dates_str = item.get("dates", "")
            start_d = dates_str.split("-")[0].strip() if "-" in dates_str else dates_str
            end_d = dates_str.split("-")[-1].strip() if "-" in dates_str else "present"
            
            entry = {
                "company": item.get("company", "").strip() or "Company",
                "position": item.get("role", "").strip() or "Role",
                "start_date": clean_date_str(start_d, is_end_date=False),
                "end_date": clean_date_str(end_d, is_end_date=True),
                "highlights": item.get("points", [])
            }
            exp_entries.append(entry)
        if exp_entries:
            sections[labels["experience"]] = exp_entries
            
    # 3. Education
    edu_list = parsed_data.get("education", [])
    if edu_list and isinstance(edu_list, list):
        edu_entries = []
        for item in edu_list:
            if not isinstance(item, dict):
                continue
            degree = item.get("degree", "").strip()
            if item.get("gpa"):
                degree += f" (GPA: {item.get('gpa')})"
            dates_str = item.get("dates", "")
            start_d = dates_str.split("-")[0].strip() if "-" in dates_str else dates_str
            end_d = dates_str.split("-")[-1].strip() if "-" in dates_str else "2022"
            
            entry = {
                "institution": item.get("school", "").strip() or "University",
                "area": degree or "Degree",
                "start_date": clean_date_str(start_d, is_end_date=False),
                "end_date": clean_date_str(end_d, is_end_date=False),
            }
            edu_entries.append(entry)
        if edu_entries:
            sections[labels["education"]] = edu_entries
            
    # 4. Skills
    skills_list = parsed_data.get("skills", [])
    if skills_list and isinstance(skills_list, list):
        skill_entries = []
        for item in skills_list:
            if not isinstance(item, dict):
                continue
            category = item.get("category", "General").strip()
            items = item.get("items", [])
            details_str = ", ".join(items) if isinstance(items, list) else str(items)
            skill_entries.append({
                "label": category,
                "details": details_str
            })
        if skill_entries:
            sections[labels["skills"]] = skill_entries

    # 5. Projects
    proj_list = parsed_data.get("projects", [])
    if proj_list and isinstance(proj_list, list):
        proj_entries = []
        for item in proj_list:
            if not isinstance(item, dict):
                continue
            date_raw = item.get("dates", "")
            entry = {
                "name": item.get("name", "").strip() or "Project",
                "date": clean_date_str(date_raw, is_end_date=False),
                "highlights": item.get("points", [])
            }
            proj_entries.append(entry)
        if proj_entries:
            sections[labels["projects"]] = proj_entries

    # 6. Achievements
    ach_list = parsed_data.get("achievements", [])
    if ach_list and isinstance(ach_list, list) and len(ach_list) > 0:
        sections[labels["achievements"]] = [str(ach) for ach in ach_list]

    cv_info["sections"] = sections
    
    valid_themes = ["sb2nov", "classic", "moderncv"]
    selected_theme = theme.lower().strip() if theme and theme.lower().strip() in valid_themes else "sb2nov"
    
    return {
        "cv": cv_info,
        "design": {
            "theme": selected_theme
        }
    }

def render_cv_with_rendercv(parsed_data: Dict[str, Any], output_path: str, theme: str = "sb2nov") -> str:
    """
    Renders CV to PDF using RenderCV Python API.
    Returns the absolute path to the generated PDF.
    """
    rendercv_dict = convert_llm_json_to_rendercv_dict(parsed_data, theme=theme)
    json_str = json.dumps(rendercv_dict, ensure_ascii=False)
    
    # Build RenderCV Model
    d, rendercv_model = build_rendercv_dictionary_and_model(json_str)
    
    # Generate Typst & PDF
    typst_path = generate_typst(rendercv_model)
    pdf_generated_path = generate_pdf(rendercv_model, typst_path)
    
    if not pdf_generated_path or not os.path.exists(pdf_generated_path):
        raise FileNotFoundError(f"RenderCV did not produce expected PDF at {pdf_generated_path}")
        
    # Copy final PDF to target output_path
    shutil.copy(pdf_generated_path, output_path)
    return output_path
