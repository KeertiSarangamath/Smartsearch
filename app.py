import io
import logging
import re
import sys
import traceback
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
from config import Config
from models import db, User, ResearchPaper, PaperSection, Source
from services.semantic_scholar import search_papers
from services.gemini_service import generate_paper, regenerate_section
from services.export_service import generate_pdf, generate_docx

# Configure logging to write immediately to debug.log and stdout
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler("debug.log", mode="a", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ],
    force=True
)

# Create the Flask application instance
app = Flask(__name__)

# Load configuration settings from config.py
app.config.from_object(Config)

# Initialize SQLAlchemy database extension with this Flask app
db.init_app(app)

# Helper Function: Fetch currently logged-in user from Flask session
def get_current_user():
    """Retrieves the User object for the currently active session user ID."""
    user_id = session.get("user_id")
    if user_id:
        return User.query.get(user_id)
    return None

# Initialize database tables automatically when app launches
with app.app_context():
    db.create_all()


# --- APP ROUTES ---

@app.route('/')
def home():
    """Home Route: Redirects to dashboard if logged in, otherwise to login page."""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login Route: Handles user authentication using simple Flask sessions."""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # Find user by username
        user = User.query.filter_by(username=username).first()

        # Check if user exists and password hash matches
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'danger')

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    """Register Route: Creates a new user account with username and password."""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        # Check if passwords match
        if password != confirm_password:
            flash('Passwords do not match. Please try again.', 'danger')
            return redirect(url_for('register'))

        # Check password length (must be at least 5 characters)
        if len(password) < 5:
            flash('Password must be at least 5 characters.', 'danger')
            return redirect(url_for('register'))

        # Check if username already exists in SQLite
        existing_user = User.query.filter_by(username=username).first()

        if existing_user:
            flash('Username is already taken. Please choose another.', 'warning')
            return redirect(url_for('register'))

        # Create new user with hashed password
        new_user = User(username=username)
        new_user.set_password(password)

        db.session.add(new_user)
        db.session.commit()

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/logout')
def logout():
    """Logout Route: Clears session user data."""
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


@app.route('/dashboard')
def dashboard():
    """Dashboard Route: Shows user's past research papers and history."""
    user = get_current_user()
    if not user:
        flash('Please log in to access the dashboard.', 'warning')
        return redirect(url_for('login'))

    # Retrieve all research papers created by this user
    user_papers = ResearchPaper.query.filter_by(user_id=user.id).order_by(ResearchPaper.created_at.desc()).all()
    return render_template('dashboard.html', user=user, papers=user_papers)


# Helper Function: Generate user-friendly flash message from Gemini API errors
def get_gemini_error_message(e, default_context="Paper generation"):
    err_str = str(e).lower()
    if "quota" in err_str or "429" in err_str:
        return "Gemini API daily limit reached. Please try again later or check your API billing."
    elif "api key" in err_str or "api_key_invalid" in err_str:
        return "Gemini API key is invalid. Please check your .env file."
    else:
        return f"{default_context} failed due to an AI service error. Please try again."


@app.route('/generator', methods=['GET', 'POST'])
def generator():
    """Generator Route: Executes OpenAlex search & Gemini AI paper generation."""
    user = get_current_user()
    if not user:
        flash('Please log in to generate research papers.', 'warning')
        return redirect(url_for('login'))

    if request.method == 'POST':
        topic = request.form.get('topic')
        paper_length = request.form.get('paper_length', 'medium')
        source_count = int(request.form.get('source_count', 5))
        citation_style = request.form.get('citation_style', 'IEEE')

        # Log received topic at start of POST request
        logging.debug(f"[GENERATOR ROUTE] Received topic: {topic}")

        # Step 1: Create a new ResearchPaper record with status 'generating'
        paper = ResearchPaper(
            user_id=user.id,
            topic=topic,
            paper_length=paper_length,
            source_count=source_count,
            citation_style=citation_style,
            status='generating'
        )
        db.session.add(paper)
        db.session.commit()

        try:
            # Step 2: Fetch academic papers using search_papers API with explicit exception handling
            try:
                fetched_sources = search_papers(topic, source_count=source_count)
            except Exception as search_err:
                logging.error(f"[SEARCH EXCEPTION] {str(search_err)}", exc_info=True)
                fetched_sources = []

            if not fetched_sources:
                flash(f'No academic sources found for topic "{topic}". Please try a different topic.', 'warning')
                db.session.delete(paper)
                db.session.commit()
                return redirect(url_for('generator'))

            # Step 3: Save retrieved source papers to database
            for src_data in fetched_sources:
                source_entry = Source(
                    paper_id=paper.id,
                    title=src_data.get('title'),
                    authors=src_data.get('authors'),
                    abstract=src_data.get('abstract'),
                    url=src_data.get('url'),
                    publication_year=src_data.get('year')
                )
                db.session.add(source_entry)
            db.session.commit()

            # Step 4: Generate paper sections using Google Gemini API
            sections_dict = generate_paper(topic, fetched_sources, paper_length=paper_length, citation_style=citation_style)

            if not sections_dict:
                raise Exception("Gemini API returned empty paper sections.")

            # Step 5: Save each section into database with explicit sequence order
            section_order_list = [
                "Title", "Abstract", "Keywords", "Introduction",
                "Literature Review", "Methodology", "Results", "Discussion", "Conclusion"
            ]

            for index, section_name in enumerate(section_order_list, start=1):
                content = sections_dict.get(section_name, "")
                section_entry = PaperSection(
                    paper_id=paper.id,
                    section_name=section_name,
                    content=content,
                    order=index
                )
                db.session.add(section_entry)

            # Step 6: Mark paper generation as completed
            paper.status = 'completed'
            db.session.commit()

            flash(f'Research paper successfully generated for topic: "{topic}"!', 'success')
            return redirect(url_for('paper_view', paper_id=paper.id))

        except Exception as e:
            # Step 7: Handle any generation errors, delete failed ResearchPaper and flash error
            logging.error(f"[GENERATION EXCEPTION] {str(e)}", exc_info=True)
            db.session.rollback()
            try:
                db.session.delete(paper)
                db.session.commit()
            except Exception as del_err:
                db.session.rollback()
                logging.error(f"[DELETE FAILED PAPER ERROR] {str(del_err)}", exc_info=True)

            error_msg = get_gemini_error_message(e, default_context="Paper generation")
            flash(error_msg, 'danger')
            return redirect(url_for('generator'))

    return render_template('generator.html', user=user)


@app.route('/paper/<int:paper_id>')
def paper_view(paper_id):
    """Paper View Route: Displays paper details and ordered sections for editing & viewing."""
    user = get_current_user()
    if not user:
        flash('Please log in to view research papers.', 'warning')
        return redirect(url_for('login'))

    paper = ResearchPaper.query.get_or_404(paper_id)

    # Security Check: Ensure paper belongs to the logged-in user
    if paper.user_id != user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))

    # Fetch sections sorted in correct sequence order
    sections = PaperSection.query.filter_by(paper_id=paper.id).order_by(PaperSection.order.asc()).all()

    return render_template('paper_view.html', paper=paper, sections=sections, sources=paper.sources)


@app.route('/paper/<int:paper_id>/section/<int:section_id>/save', methods=['POST'])
def save_section(paper_id, section_id):
    """Save Route: Updates user text edits for a specific paper section in SQLite."""
    user = get_current_user()
    if not user:
        flash('Please log in to save changes.', 'warning')
        return redirect(url_for('login'))

    paper = ResearchPaper.query.get_or_404(paper_id)
    if paper.user_id != user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))

    section = PaperSection.query.get_or_404(section_id)
    edited_content = request.form.get('content', '')

    if section.paper_id == paper.id:
        section.content = edited_content
        db.session.commit()
        flash(f'Section "{section.section_name}" saved successfully!', 'success')

    return redirect(url_for('paper_view', paper_id=paper.id))


@app.route('/paper/<int:paper_id>/section/<int:section_id>/regenerate', methods=['POST'])
def regenerate_paper_section(paper_id, section_id):
    """Regenerate Route: Calls Gemini API to rewrite a specific section based on user instruction."""
    user = get_current_user()
    if not user:
        flash('Please log in to regenerate paper sections.', 'warning')
        return redirect(url_for('login'))

    paper = ResearchPaper.query.get_or_404(paper_id)
    if paper.user_id != user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))

    section = PaperSection.query.get_or_404(section_id)

    # Read optional instruction from user form, default to "improve this section"
    instruction = request.form.get('instruction', '').strip()
    if not instruction:
        instruction = "Improve and expand this section with clear academic tone and structure."

    try:
        # Fetch paper sources for context
        sources_data = [
            {
                "title": s.title,
                "authors": s.authors,
                "abstract": s.abstract,
                "url": s.url,
                "year": s.publication_year
            }
            for s in paper.sources
        ]

        # Call Gemini AI section regeneration service
        new_content = regenerate_section(
            topic=paper.topic,
            section_name=section.section_name,
            current_content=section.content,
            instruction=instruction,
            sources=sources_data,
            citation_style=paper.citation_style
        )

        section.content = new_content
        db.session.commit()
        flash(f'Section "{section.section_name}" regenerated successfully!', 'success')

    except Exception as e:
        logging.error(f"[REGENERATE EXCEPTION] {str(e)}", exc_info=True)
        error_msg = get_gemini_error_message(e, default_context="Section regeneration")
        flash(error_msg, 'danger')

    return redirect(url_for('paper_view', paper_id=paper.id))


@app.route('/sources/<int:paper_id>')
def sources_view(paper_id):
    """Sources Route: Displays cited academic papers fetched from Semantic Scholar."""
    user = get_current_user()
    if not user:
        flash('Please log in to view sources.', 'warning')
        return redirect(url_for('login'))

    paper = ResearchPaper.query.get_or_404(paper_id)

    # Security Check: Ensure paper belongs to the logged-in user
    if paper.user_id != user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))

    return render_template('sources.html', paper=paper, sources=paper.sources)


@app.route('/paper/<int:paper_id>/pdf')
def export_pdf(paper_id):
    """PDF Export Route: Generates and streams PDF download for paper."""
    user = get_current_user()
    if not user:
        flash('Please log in to download papers.', 'warning')
        return redirect(url_for('login'))

    paper = ResearchPaper.query.get_or_404(paper_id)
    if paper.user_id != user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))

    # Query sections in correct sequence order
    sections = PaperSection.query.filter_by(paper_id=paper.id).order_by(PaperSection.order.asc()).all()

    # Generate binary PDF bytes in memory
    pdf_bytes = generate_pdf(paper, sections, paper.sources)

    # Sanitize paper topic for clean download filename
    safe_topic = re.sub(r'[^\w\s-]', '', paper.topic).strip().replace(' ', '_')[:40]
    filename = f"{safe_topic}_Paper.pdf"

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )


@app.route('/paper/<int:paper_id>/docx')
def export_docx(paper_id):
    """DOCX Export Route: Generates and streams Word DOCX download for paper."""
    user = get_current_user()
    if not user:
        flash('Please log in to download papers.', 'warning')
        return redirect(url_for('login'))

    paper = ResearchPaper.query.get_or_404(paper_id)
    if paper.user_id != user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))

    # Query sections in correct sequence order
    sections = PaperSection.query.filter_by(paper_id=paper.id).order_by(PaperSection.order.asc()).all()

    # Generate binary DOCX bytes in memory
    docx_bytes = generate_docx(paper, sections, paper.sources)

    # Sanitize paper topic for clean download filename
    safe_topic = re.sub(r'[^\w\s-]', '', paper.topic).strip().replace(' ', '_')[:40]
    filename = f"{safe_topic}_Paper.docx"

    return send_file(
        io.BytesIO(docx_bytes),
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        as_attachment=True,
        download_name=filename
    )


if __name__ == '__main__':
    # Run Flask application server on http://127.0.0.1:5000
    app.run(debug=True)
