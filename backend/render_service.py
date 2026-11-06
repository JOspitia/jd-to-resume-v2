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

SPANISH_MONTHS = {
    "ene": "01", "enero": "01",
    "feb": "02", "febrero": "02",
    "mar": "03", "marzo": "03",
    "abr": "04", "abril": "04",
    "may": "05", "mayo": "05",
    "jun": "06", "junio": "06",
    "jul": "07", "julio": "07",
    "ago": "08", "agosto": "08",
    "sep": "09", "septiembre": "09", "setiembre": "09",
    "oct": "10", "octubre": "10",
    "nov": "11", "noviembre": "11",
    "dic": "12", "diciembre": "12"
}

def clean_date_str(date_val: str, is_end_date: bool = False) -> str:
    """Clean date string to match RenderCV expected format (YYYY, YYYY-MM, or 'present')."""
    if not date_val:
        return "present" if is_end_date else "2020"
    cleaned = date_val.strip().lower()
    if is_end_date and cleaned in ["presente", "present", "actualidad", "actual", "actualmente", "hoy", "now"]:
        return "present"
    
    # Check for direct YYYY-MM
    match_ym = re.search(r"\b(19\d\d|20\d\d)-(0[1-9]|1[0-2])\b", cleaned)
    if match_ym:
        return match_ym.group(0)

    # Check for Spanish or English month name + year (e.g. "Feb 2019", "Ago 2023")
    year_match = re.search(r"\b(19\d\d|20\d\d)\b", cleaned)
    if year_match:
        year = year_match.group(1)
        for m_name, m_num in SPANISH_MONTHS.items():
            if re.search(r"\b" + m_name + r"\b", cleaned):
                return f"{year}-{m_num}"
        return year
        
    return "present" if is_end_date else "2020"


# ---------------------------------------------------------------------------
# Date range parsing
# ---------------------------------------------------------------------------
#
# A range separator is a dash surrounded by whitespace (or an en/em dash, a
# pipe, or "to"/"hasta"). It must NOT match the hyphen inside a `YYYY-MM`
# date: splitting "2018-08 - 2021-05" on every hyphen produced
# ["2018", "08 ", "2021", "05"], so the end date was lost and later replaced
# by the "2020" placeholder. Whenever the start year was greater than 2020
# RenderCV rejected the whole CV ("start_date cannot be after end_date") and
# the render silently fell back to the slower Playwright HTML renderer, which
# also ignored the theme the user had picked.
_RANGE_SEPARATOR = re.compile(
    r"\s+[-–—]{1,2}\s+|\s*\|\s*|\s+(?:to|hasta)\s+", re.IGNORECASE
)
_YEAR_OR_YEAR_MONTH = re.compile(r"(?:19|20)\d{2}(?:-(?:0[1-9]|1[0-2]))?")
_PRESENT_WORDS = (
    "presente",
    "present",
    "actualidad",
    "actual",
    "actualmente",
    "hoy",
    "now",
    "current",
)


def split_date_range(dates_str: str) -> tuple[str, str]:
    """Split a free-form date range into ``(start, end)``.

    Handles the shapes the LLM actually emits::

        "2018-08 - 2021-05"    ->  ("2018-08", "2021-05")
        "2021 - hoy"           ->  ("2021", "hoy")
        "Sept 2019 - Feb 2021" ->  ("Sept 2019", "Feb 2021")
        "2018"                 ->  ("2018", "")
        "2018-2021"            ->  ("2018", "2021")
    """
    text = (dates_str or "").strip()
    if not text:
        return "", ""

    parts = [part.strip() for part in _RANGE_SEPARATOR.split(text) if part.strip()]
    if len(parts) >= 2:
        return parts[0], parts[-1]

    # No whitespace-delimited separator ("2018-2021"): split between the two
    # date tokens instead of on every hyphen.
    tokens = list(_YEAR_OR_YEAR_MONTH.finditer(text))
    if len(tokens) >= 2:
        return (
            text[tokens[0].start() : tokens[0].end()],
            text[tokens[-1].start() : tokens[-1].end()],
        )

    return (parts[0] if parts else text), ""


def clean_date_optional(date_val: str) -> Optional[str]:
    """Parse a date into RenderCV's format, or ``None`` when there is none.

    Unlike :func:`clean_date_str` this never substitutes a placeholder year:
    a fabricated "2020" would show up in the finished PDF as if the candidate
    had started in 2020.
    """
    if not date_val or not date_val.strip():
        return None
    cleaned = date_val.strip().lower()

    if cleaned in _PRESENT_WORDS:
        return "present"

    match_ym = re.search(r"\b(19\d\d|20\d\d)-(0[1-9]|1[0-2])\b", cleaned)
    if match_ym:
        return match_ym.group(0)

    year_match = re.search(r"\b(19\d\d|20\d\d)\b", cleaned)
    if year_match:
        year = year_match.group(1)
        for m_name, m_num in SPANISH_MONTHS.items():
            if re.search(r"\b" + m_name + r"\b", cleaned):
                return f"{year}-{m_num}"
        return year

    return None


def _date_year(date_str: Optional[str]) -> Optional[int]:
    """Extract the year from a parsed date, or ``None`` when unknown."""
    match = re.search(r"(?:19|20)\d{2}", date_str or "")
    return int(match.group(0)) if match else None


def resolve_date_pair(
    start_raw: str,
    end_raw: str,
    *,
    default_end: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    """Clean a date pair and guarantee RenderCV will accept it.

    RenderCV rejects the *entire* CV when ``start_date`` is after
    ``end_date``. Instead of emitting an invalid pair (which silently pushed
    every render onto the slower Playwright fallback), an inconsistent range
    drops the end date — RenderCV accepts an entry without ``end_date``.

    Both fields are optional in RenderCV, so a date that cannot be parsed is
    omitted rather than replaced with a made-up year.
    """
    start = clean_date_optional(start_raw)
    if start is None:
        # No start date at all: omit the end date too, otherwise the entry
        # renders a bare "present" with no context to anchor it.
        return None, None

    end = clean_date_optional(end_raw) if end_raw else default_end

    start_year = _date_year(start)
    end_year = _date_year(end)
    if start_year and end_year and start_year > end_year:
        return start, None
    return start, end

def convert_llm_json_to_rendercv_dict(
    parsed_data: Dict[str, Any],
    theme: str = "sb2nov",
    fit_single_page: bool = False,
    photo_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Transforms the LLM output structure into RenderCV valid schema.
    Applies localized section titles from `section_labels`.

    When `fit_single_page` is set, tightens page margins, line spacing and
    section spacing so a long CV is pushed back onto a single page.

    When `photo_path` is set, embeds the candidate photo in the header.
    """
    name = parsed_data.get("name", "Candidate").strip() or "Candidate"
    email = parsed_data.get("email", "").strip()
    phone = sanitize_phone(parsed_data.get("phone", ""))
    location = parsed_data.get("location", "").strip()
    
    cv_info: Dict[str, Any] = {
        "name": name,
    }
    if location:
        cv_info["location"] = location
    if email:
        cv_info["email"] = email
    if phone:
        cv_info["phone"] = phone
    # RenderCV resolves this against the filesystem, so only pass it when the
    # file still exists — a stale path makes the whole render fail and silently
    # drop the CV onto the Playwright fallback.
    if photo_path and os.path.isfile(photo_path):
        cv_info["photo"] = photo_path

        
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
            start_d, end_d = split_date_range(dates_str)

            start_date, end_date = resolve_date_pair(
                start_d, end_d, default_end="present"
            )

            entry = {
                "company": item.get("company", "").strip() or "Company",
                "position": item.get("role", "").strip() or "Role",
                "highlights": item.get("points", [])
            }
            if start_date:
                entry["start_date"] = start_date
            if end_date:
                entry["end_date"] = end_date
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
            start_d, end_d = split_date_range(dates_str)

            # A degree with no end date is normal (still studying), and
            # RenderCV renders the entry without one.
            start_date, end_date = resolve_date_pair(start_d, end_d)

            entry = {
                "institution": item.get("school", "").strip() or "University",
                "area": degree or "Degree",
            }
            if start_date:
                entry["start_date"] = start_date
            if end_date:
                entry["end_date"] = end_date
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
            highlights = list(item.get("points", []))

            # Prepend URL links as the first highlight line so they appear in the PDF
            links = []
            proj_url = item.get("url", "").strip()
            proj_github = item.get("github_url", "").strip()
            if proj_url:
                links.append(proj_url)
            if proj_github and proj_github != proj_url:
                links.append(proj_github)
            if links:
                highlights = [" | ".join(links)] + highlights

            entry = {
                "name": item.get("name", "").strip() or "Project",
                "highlights": highlights
            }
            project_date = clean_date_optional(date_raw)
            if project_date:
                entry["date"] = project_date
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
    
    # Custom design configuration for clean layout & orphan avoidance
    design_config: Dict[str, Any] = {
        "theme": selected_theme,
        "entries": {
            # STRICT ANTI-ORPHAN: Never break an individual job / project across pages
            "allow_page_break": False,
            "highlights": {
                "space_between_items": "0.1em",
                "space_above": "0.1em"
            }
        },
        "sections": {
            "space_between_regular_entries": "0.8em",
            "space_between_text_based_entries": "0.25em"
        },
        "section_titles": {
            "space_above": "0.4cm",
            "space_below": "0.2cm"
        }
    }

    # If fit_single_page requested, tighten vertical margins and line spacing
    if fit_single_page:
        design_config["page"] = {
            "top_margin": "0.45in",
            "bottom_margin": "0.45in",
            "left_margin": "0.5in",
            "right_margin": "0.5in"
        }
        design_config["typography"] = {
            "line_spacing": "0.45em"
        }
        design_config["sections"]["space_between_regular_entries"] = "0.6em"
        design_config["section_titles"]["space_above"] = "0.3cm"
        design_config["section_titles"]["space_below"] = "0.15cm"

    return {
        "cv": cv_info,
        "design": design_config
    }

def render_cv_with_rendercv(
    parsed_data: Dict[str, Any], 
    output_path: str, 
    theme: str = "sb2nov", 
    fit_single_page: bool = False,
    page_break_section: Optional[str] = None,
    photo_path: Optional[str] = None
) -> str:
    """
    Renders CV to PDF using RenderCV Python API.
    Returns the absolute path to the generated PDF.
    """
    # convert_llm_json_to_rendercv_dict applies the compact layout internally
    # when fit_single_page is set (margins, line spacing, section spacing), so
    # it must be forwarded here. Passing it previously raised TypeError, which
    # silently pushed every RenderCV render onto the Playwright fallback.
    rendercv_dict = convert_llm_json_to_rendercv_dict(
        parsed_data, 
        theme=theme, 
        fit_single_page=fit_single_page,
        photo_path=photo_path
    )
    json_str = json.dumps(rendercv_dict, ensure_ascii=False)
    
    # Build RenderCV Model
    d, rendercv_model = build_rendercv_dictionary_and_model(json_str)
    
    # Generate Typst
    typst_path = generate_typst(rendercv_model)

    # If manual page break before a specific section is requested, insert it directly in the Typst file
    if page_break_section and os.path.exists(typst_path):
        try:
            with open(typst_path, "r", encoding="utf-8") as f:
                typst_code = f.read()

            # Search section title heading pattern in Typst, e.g. == Experience or = Experience
            pattern = rf"(==\s*\[?{re.escape(page_break_section)}\]?)"
            if re.search(pattern, typst_code, flags=re.IGNORECASE):
                typst_code = re.sub(pattern, r"#pagebreak()\n\1", typst_code, count=1, flags=re.IGNORECASE)
                with open(typst_path, "w", encoding="utf-8") as f:
                    f.write(typst_code)
                print(f"[INFO] 📄 Injected #pagebreak() before section: {page_break_section}")
        except Exception as pb_err:
            print(f"[WARN] Could not inject pagebreak into Typst: {pb_err}")

    # Generate PDF from Typst
    pdf_generated_path = generate_pdf(rendercv_model, typst_path)
    
    if not pdf_generated_path or not os.path.exists(pdf_generated_path):
        raise FileNotFoundError(f"RenderCV did not produce expected PDF at {pdf_generated_path}")
        
    # Copy final PDF to target output_path
    shutil.copy(pdf_generated_path, output_path)
    return output_path

