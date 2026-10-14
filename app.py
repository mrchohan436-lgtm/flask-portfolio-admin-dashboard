

from multiprocessing import connection
import csv
import io

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    Response
)
import smtplib
from datetime import datetime
from email.message import EmailMessage
import sqlite3
from pathlib import Path
from functools import wraps
from dotenv import load_dotenv, set_key
import os
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash

from flask_wtf.csrf import CSRFProtect

load_dotenv()

app = Flask(__name__)

MAIL_SERVER = os.getenv("MAIL_SERVER")
MAIL_PORT = int(os.getenv("MAIL_PORT", 587))
MAIL_USERNAME = os.getenv("MAIL_USERNAME")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER")

# Flask session secret
app.secret_key = os.getenv("SECRET_KEY")
app.config["WTF_CSRF_TIME_LIMIT"] = 28800
csrf = CSRFProtect(app)

DATABASE = Path("instance/contacts.db")


# =========================
# ADMIN LOGIN
# =========================

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH")


# =========================
# DATABASE CONNECTION
# =========================

def get_db_connection():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection

def send_reply_email(to_email, reply_text, name):
    message = EmailMessage()

    message["Subject"] = "Reply to Your Message - Portfolio"
    message["From"] = MAIL_DEFAULT_SENDER
    message["To"] = to_email

    # Plain-text fallback
    message.set_content(
        f"""Hello {name},

Thank you for contacting us.

Here is our reply:

{reply_text}

Best regards,
Portfolio Team
"""
    )

    # Professional HTML email
    html_content = render_template(
        "email_templates/reply_email.html",
        name=name,
        reply=reply_text
    )

    message.add_alternative(
        html_content,
        subtype="html"
    )

    # Gmail SMTP - STARTTLS
    with smtplib.SMTP(MAIL_SERVER, MAIL_PORT) as server:
        server.starttls()
        server.login(
            MAIL_USERNAME,
            MAIL_PASSWORD
        )
        server.send_message(message)


def send_admin_notification(name, email, message_text):
    message = EmailMessage()

    message["Subject"] = "New Contact Message - Portfolio"
    message["From"] = MAIL_DEFAULT_SENDER
    message["To"] = MAIL_USERNAME

    # Plain-text fallback
    message.set_content(
        f"""Hello Admin,

You have received a new message through your portfolio website.

Name: {name}
Email: {email}

Message:
{message_text}

Please login to the admin panel to view and reply.

Best regards,
Portfolio System
"""
    )

    # HTML email
    html_content = render_template(
        "email_templates/new_message.html",
        name=name,
        email=email,
        message=message_text
    )

    message.add_alternative(
        html_content,
        subtype="html"
    )

    # Send email using Gmail STARTTLS
    with smtplib.SMTP(MAIL_SERVER, MAIL_PORT) as server:
        server.starttls()
        server.login(
            MAIL_USERNAME,
            MAIL_PASSWORD
        )
        server.send_message(message)

# =========================
# DATABASE INITIALIZATION
# =========================

def init_db():

    DATABASE.parent.mkdir(exist_ok=True)

    connection = sqlite3.connect(DATABASE)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            message TEXT NOT NULL,
            status TEXT DEFAULT 'New',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Check existing columns
    columns = connection.execute(
        "PRAGMA table_info(contacts)"
    ).fetchall()

    column_names = [column[1] for column in columns]

    # =========================
    # ADD STATUS COLUMN
    # =========================

    if "status" not in column_names:
        connection.execute("""
            ALTER TABLE contacts
            ADD COLUMN status TEXT DEFAULT 'New'
        """)

    # =========================
    # ADD REPLY COLUMN
    # =========================

    if "reply" not in column_names:
        connection.execute("""
            ALTER TABLE contacts
            ADD COLUMN reply TEXT
        """)

    # =========================
    # ADD REPLIED AT COLUMN
    # =========================

    if "replied_at" not in column_names:
        connection.execute("""
            ALTER TABLE contacts
            ADD COLUMN replied_at TIMESTAMP
        """)

    # =========================
    # ADD REPLIED BY COLUMN
    # =========================

    if "replied_by" not in column_names:
        connection.execute("""
            ALTER TABLE contacts
            ADD COLUMN replied_by TEXT
        """)


    # =========================
    # ACTIVITY LOGS TABLE
    # =========================

    connection.execute("""
        CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_username TEXT,
            action TEXT NOT NULL,
            description TEXT,
            message_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # =========================
    # MESSAGE INTELLIGENCE
    # =========================

    # Refresh column list after existing migrations
    columns = connection.execute(
        "PRAGMA table_info(contacts)"
    ).fetchall()

    column_names = [column[1] for column in columns]

    # Sentiment
    if "sentiment" not in column_names:
        connection.execute("""
            ALTER TABLE contacts
            ADD COLUMN sentiment TEXT DEFAULT 'Neutral'
        """)

    # Priority
    if "priority" not in column_names:
        connection.execute("""
            ALTER TABLE contacts
            ADD COLUMN priority TEXT DEFAULT 'Medium'
        """)

    # Category
    if "category" not in column_names:
        connection.execute("""
            ALTER TABLE contacts
            ADD COLUMN category TEXT DEFAULT 'General'
        """)

    # Intent
    if "intent" not in column_names:
        connection.execute("""
            ALTER TABLE contacts
            ADD COLUMN intent TEXT DEFAULT 'General Inquiry'
        """)

    # Intelligence Score
    if "intelligence_score" not in column_names:
        connection.execute("""
            ALTER TABLE contacts
            ADD COLUMN intelligence_score INTEGER DEFAULT 50
        """)

    # AI Summary
    if "ai_summary" not in column_names:
        connection.execute("""
            ALTER TABLE contacts
            ADD COLUMN ai_summary TEXT
        """)

    connection.commit()
    connection.close()

# =========================
#      ACTIVITY LOG
# =========================

def log_activity(action, description=None, message_id=None):

    connection = get_db_connection()

    connection.execute("""
        INSERT INTO activity_logs (
            admin_username,
            action,
            description,
            message_id
        )
        VALUES (?, ?, ?, ?)
    """, (
        session.get("admin_username", "Admin"),
        action,
        description,
        message_id
    ))

    connection.commit()
    connection.close()

# =========================
# ADMIN PROTECTION
# =========================

def admin_required(route_function):

    @wraps(route_function)
    def protected_route(*args, **kwargs):

        if not session.get("admin_logged_in"):

            return redirect(
                url_for("admin_login")
            )

        return route_function(*args, **kwargs)

    return protected_route
# =========================
# ADMIN NOTIFICATIONS
# =========================

@app.context_processor
def inject_admin_notifications():

    if not session.get("admin_logged_in"):
        return {}

    connection = get_db_connection()

    new_message_count = connection.execute(
        """
        SELECT COUNT(*)
        FROM contacts
        WHERE status = 'New'
        """
    ).fetchone()[0]

    connection.close()

    return {
        "new_message_count": new_message_count
    }

# =========================
# MESSAGE INTELLIGENCE ENGINE
# =========================

def analyze_message(message):

    text = message.lower().strip()

    # =========================
    # SENTIMENT
    # =========================

    positive_words = [
        "thanks",
        "thank you",
        "great",
        "excellent",
        "amazing",
        "good",
        "love",
        "appreciate",
        "helpful",
        "awesome",
        "happy",
        "perfect"
    ]

    negative_words = [
        "bad",
        "poor",
        "terrible",
        "hate",
        "angry",
        "problem",
        "issue",
        "wrong",
        "disappointed",
        "unhappy",
        "urgent",
        "failed"
    ]

    positive_count = sum(
        1 for word in positive_words
        if word in text
    )

    negative_count = sum(
        1 for word in negative_words
        if word in text
    )

    if positive_count > negative_count:
        sentiment = "Positive"

    elif negative_count > positive_count:
        sentiment = "Negative"

    else:
        sentiment = "Neutral"


    # =========================
    # PRIORITY
    # =========================

    high_priority_words = [
        "urgent",
        "asap",
        "immediately",
        "critical",
        "emergency",
        "deadline",
        "today",
        "important"
    ]

    medium_priority_words = [
        "soon",
        "quickly",
        "problem",
        "issue",
        "help",
        "request"
    ]

    if any(word in text for word in high_priority_words):
        priority = "High"

    elif any(word in text for word in medium_priority_words):
        priority = "Medium"

    else:
        priority = "Low"


    # =========================
    # CATEGORY
    # =========================

    if any(word in text for word in [
        "website",
        "web",
        "flask",
        "python",
        "application",
        "app",
        "software",
        "development",
        "developer",
        "coding"
    ]):
        category = "Development"

    elif any(word in text for word in [
        "business",
        "company",
        "startup",
        "project",
        "client",
        "service"
    ]):
        category = "Business"

    elif any(word in text for word in [
        "collaboration",
        "collaborate",
        "partnership",
        "partner",
        "work together",
        "freelance"
    ]):
        category = "Collaboration"

    elif any(word in text for word in [
        "support",
        "problem",
        "issue",
        "error",
        "bug",
        "help"
    ]):
        category = "Support"

    else:
        category = "General"


    # =========================
    # INTENT
    # =========================

    if any(word in text for word in [
        "hire",
        "hiring",
        "job",
        "developer needed",
        "work with"
    ]):
        intent = "Hiring / Job Opportunity"

    elif any(word in text for word in [
        "price",
        "cost",
        "budget",
        "pricing",
        "quote",
        "quotation"
    ]):
        intent = "Pricing Inquiry"

    elif any(word in text for word in [
        "collaboration",
        "collaborate",
        "partnership",
        "partner"
    ]):
        intent = "Collaboration Request"

    elif any(word in text for word in [
        "help",
        "support",
        "problem",
        "issue",
        "error",
        "bug"
    ]):
        intent = "Support Request"

    elif any(word in text for word in [
        "hello",
        "hi",
        "hey",
        "contact",
        "message"
    ]):
        intent = "General Inquiry"

    else:
        intent = "Information Request"


    # =========================
    # INTELLIGENCE SCORE
    # =========================

    score = 50

    if priority == "High":
        score += 25

    elif priority == "Medium":
        score += 10

    if category != "General":
        score += 10

    if intent != "General Inquiry":
        score += 10

    if sentiment == "Negative":
        score += 5

    # Maximum score = 100
    score = min(score, 100)


    # =========================
    # SUMMARY
    # =========================

    words = message.strip().split()

    if len(words) <= 12:
        summary = message.strip()

    else:
        summary = " ".join(words[:12]) + "..."


    return {
        "sentiment": sentiment,
        "priority": priority,
        "category": category,
        "intent": intent,
        "intelligence_score": score,
        "ai_summary": summary
    }

# =========================
# HOME
# =========================

@app.route("/")
def home():

    return render_template("index.html")


# =========================
# CONTACT FORM
# =========================

@app.route("/contact", methods=["POST"])
def contact():

    name = request.form.get("name", "").strip()

    email = request.form.get("email", "").strip()

    message = request.form.get("message", "").strip()

    if not name or not email or not message:
        return "Please fill in all fields.", 400

    connection = get_db_connection()

    # =========================
    # MESSAGE INTELLIGENCE
    # =========================

    intelligence = analyze_message(message)


    # =========================
    # SAVE MESSAGE + INTELLIGENCE
    # =========================

    connection.execute("""
        INSERT INTO contacts (
            name,
            email,
            message,
            sentiment,
            priority,
            category,
            intent,
            intelligence_score,
            ai_summary
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        name,
        email,
        message,
        intelligence["sentiment"],
        intelligence["priority"],
        intelligence["category"],
        intelligence["intent"],
        intelligence["intelligence_score"],
        intelligence["ai_summary"]
    ))

    connection.commit()
    connection.close()

    try:

        send_admin_notification(
            name,
            email,
            message
        )

    except Exception as e:

        print("ADMIN EMAIL ERROR:", repr(e))

    return f"Thank you, {name}! Your message was saved successfully."
# =========================
# ADMIN LOGIN
# =========================

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():

    if session.get("admin_logged_in"):
        return redirect(
            url_for("admin_dashboard")
        )

    error = None

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        if (
            username == ADMIN_USERNAME
            and ADMIN_PASSWORD_HASH
            and check_password_hash(
                ADMIN_PASSWORD_HASH,
                password
            )
        ):

            session["admin_logged_in"] = True
            session["admin_username"] = username

            log_activity(
                "Login",
                "Admin logged into the dashboard"
            )

            return redirect(
                url_for("admin_dashboard")
            )

        error = "Invalid username or password."

    return render_template(
        "admin_login.html",
        error=error
    )
# =========================
# ADMIN LOGOUT
# =========================

@app.route("/admin/logout")
def admin_logout():

    log_activity(
        "Logout",
        "Admin logged out of the dashboard"
    )

    session.clear()

    return redirect(
        url_for("admin_login")
    )
# =========================
# ADMIN SETTINGS
# =========================

@app.route("/admin/settings", methods=["GET", "POST"])
@admin_required
def admin_settings():

    global ADMIN_PASSWORD_HASH

    if request.method == "POST":

        current_password = request.form.get(
            "current_password",
            ""
        )

        new_password = request.form.get(
            "new_password",
            ""
        )

        confirm_password = request.form.get(
            "confirm_password",
            ""
        )

        # =========================
        # CHECK CURRENT PASSWORD
        # =========================

        if not check_password_hash(
            ADMIN_PASSWORD_HASH,
            current_password
        ):

            flash(
                "Current password is incorrect.",
                "error"
            )

            return redirect(
                url_for("admin_settings")
            )

        # =========================
        # PASSWORD LENGTH
        # =========================

        if len(new_password) < 8:

            flash(
                "New password must be at least 8 characters.",
                "error"
            )

            return redirect(
                url_for("admin_settings")
            )

        # =========================
        # CONFIRM PASSWORD
        # =========================

        if new_password != confirm_password:

            flash(
                "New passwords do not match.",
                "error"
            )

            return redirect(
                url_for("admin_settings")
            )

        # =========================
        # GENERATE NEW HASH
        # =========================

        new_password_hash = generate_password_hash(
            new_password
        )

        # =========================
        # UPDATE .ENV
        # =========================

        set_key(
            ".env",
            "ADMIN_PASSWORD_HASH",
            new_password_hash
        )

        # Update current application variable
        ADMIN_PASSWORD_HASH = new_password_hash

        # =========================
        # ACTIVITY LOG
        # =========================

        log_activity(
            "Password Changed",
            "Admin changed the account password"
        )

        flash(
            "Password changed successfully.",
            "success"
        )

        return redirect(
            url_for("admin_settings")
        )

    return render_template(
        "admin_settings.html"
    )

# =========================
# ADMIN DASHBOARD
# =========================

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():

    connection = get_db_connection()

    total_messages = connection.execute(
        """
        SELECT COUNT(*)
        FROM contacts
        """
    ).fetchone()[0]

    new_messages = connection.execute(
        """
        SELECT COUNT(*)
        FROM contacts
        WHERE status = 'New'
        """
    ).fetchone()[0]

    read_messages = connection.execute(
        """
        SELECT COUNT(*)
        FROM contacts
        WHERE status = 'Read'
        """
    ).fetchone()[0]

    replied_messages = connection.execute(
        """
        SELECT COUNT(*)
        FROM contacts
        WHERE status = 'Replied'
        """
    ).fetchone()[0]

    recent_messages = connection.execute(
        """
        SELECT *
        FROM contacts
        ORDER BY created_at DESC
        LIMIT 5
        """
    ).fetchall()

        # =========================
    # NOTIFICATION MESSAGES
    # =========================

    notification_messages = connection.execute(
        """
        SELECT *
        FROM contacts
        WHERE status = 'New'
        ORDER BY created_at DESC
        """
    ).fetchall()

    # =========================
    # ACTIVITY LOG STATISTICS
    # =========================

    total_activities = connection.execute(
        """
        SELECT COUNT(*)
        FROM activity_logs
        """
    ).fetchone()[0]

    total_logins = connection.execute(
        """
        SELECT COUNT(*)
        FROM activity_logs
        WHERE action = 'Login'
        """
    ).fetchone()[0]

    total_replies = connection.execute(
    "SELECT COUNT(*) FROM contacts WHERE status = 'Replied'"
).fetchone()[0]

    # =========================
    # INTELLIGENCE OVERVIEW
    # =========================

    # -------------------------
    # SENTIMENT OVERVIEW
    # -------------------------

    sentiment_data = connection.execute(
        """
        SELECT sentiment, COUNT(*) AS total
        FROM contacts
        WHERE sentiment IS NOT NULL
        AND sentiment != ''
        GROUP BY sentiment
        ORDER BY total DESC
        """
    ).fetchall()

    if sentiment_data:
        dominant_sentiment = sentiment_data[0]["sentiment"]
        dominant_sentiment_count = sentiment_data[0]["total"]
    else:
        dominant_sentiment = "No Data"
        dominant_sentiment_count = 0

    # -------------------------
    # PRIORITY OVERVIEW
    # -------------------------

    priority_data = connection.execute(
        """
        SELECT priority, COUNT(*) AS total
        FROM contacts
        WHERE priority IS NOT NULL
        AND priority != ''
        GROUP BY priority
        ORDER BY total DESC
        """
    ).fetchall()

    if priority_data:
        dominant_priority = priority_data[0]["priority"]
        dominant_priority_count = priority_data[0]["total"]
    else:
        dominant_priority = "No Data"
        dominant_priority_count = 0

    # -------------------------
    # REPLY PERFORMANCE
    # -------------------------

    if total_messages > 0:
        reply_rate = round(
            (replied_messages / total_messages) * 100,
            1
        )
    else:
        reply_rate = 0

    # -------------------------
    # MESSAGE HANDLING
    # -------------------------

    handled_messages = read_messages + replied_messages

    if total_messages > 0:
        handling_rate = round(
            (handled_messages / total_messages) * 100,
            1
        )
    else:
        handling_rate = 0


    # -------------------------
    # MESSAGE TREND
    # -------------------------

    recent_7_days = connection.execute(
        """
        SELECT COUNT(*)
        FROM contacts
        WHERE datetime(created_at) >= datetime('now', '-7 days')
        """
    ).fetchone()[0]

    previous_7_days = connection.execute(
        """
        SELECT COUNT(*)
        FROM contacts
        WHERE datetime(created_at) >= datetime('now', '-14 days')
        AND datetime(created_at) < datetime('now', '-7 days')
        """
    ).fetchone()[0]

    if previous_7_days == 0:

        if recent_7_days > 0:
            message_trend = "Increasing"
        else:
            message_trend = "Stable"

        trend_percentage = 0

    else:

        trend_percentage = round(
            (
                (recent_7_days - previous_7_days)
                / previous_7_days
            ) * 100,
            1
        )

        if trend_percentage > 0:
            message_trend = "Increasing"

        elif trend_percentage < 0:
            message_trend = "Decreasing"

        else:
            message_trend = "Stable"


    # -------------------------
    # PEAK ACTIVITY DAY
    # -------------------------

    peak_activity = connection.execute(
        """
        SELECT
            strftime('%w', created_at) AS day_number,
            COUNT(*) AS total
        FROM contacts
        GROUP BY day_number
        ORDER BY total DESC
        LIMIT 1
        """
    ).fetchone()


    day_names = {
        "0": "Sunday",
        "1": "Monday",
        "2": "Tuesday",
        "3": "Wednesday",
        "4": "Thursday",
        "5": "Friday",
        "6": "Saturday"
    }


    if peak_activity:
        peak_activity_day = day_names.get(
            peak_activity["day_number"],
            "Unknown"
        )

        peak_activity_count = peak_activity["total"]

    else:
        peak_activity_day = "No Data"
        peak_activity_count = 0
        # -------------------------
    # SMART RECOMMENDATION
    # -------------------------

    if total_messages == 0:

        intelligence_status = "No Data"

        intelligence_message = (
            "There is not enough message data to generate "
            "an intelligent recommendation."
        )

    elif new_messages >= 3:

        intelligence_status = "Needs Attention"

        intelligence_message = (
            f"You currently have {new_messages} new messages "
            "waiting for attention. Prioritize these messages "
            "to improve response performance."
        )

    elif reply_rate < 50:

        intelligence_status = "Needs Attention"

        intelligence_message = (
            f"Your reply rate is {reply_rate}%. "
            "Consider responding to pending messages more quickly "
            "to improve overall engagement."
        )

    elif trend_percentage > 20:

        intelligence_status = "High Activity"

        intelligence_message = (
            f"Message activity has increased by "
            f"{trend_percentage}% compared with the previous "
            "7 days. Consider monitoring incoming messages closely."
        )

    elif dominant_priority.lower() == "high":

        intelligence_status = "Priority Alert"

        intelligence_message = (
            "High-priority messages are currently dominant. "
            "Review priority messages first to maintain fast response times."
        )

    elif dominant_sentiment.lower() == "negative":

        intelligence_status = "Sentiment Alert"

        intelligence_message = (
            "Negative sentiment is currently dominant. "
            "Consider reviewing these conversations carefully "
            "and responding professionally."
        )

    elif reply_rate >= 80:

        intelligence_status = "Excellent"

        intelligence_message = (
            f"Your reply rate is {reply_rate}%. "
            "Message response performance is excellent."
        )

    elif handling_rate >= 80:

        intelligence_status = "Good"

        intelligence_message = (
            f"You have handled {handling_rate}% of your messages. "
            "Overall message management is performing well."
        )

    else:

        intelligence_status = "Good"

        intelligence_message = (
            "Message activity is stable. Continue monitoring "
            "new messages and maintaining consistent response times."
        )

    # =========================
    # RECENT ACTIVITY
    # =========================

    recent_activities = connection.execute(
        """
        SELECT *
        FROM activity_logs
        ORDER BY created_at DESC
        LIMIT 5
        """
    ).fetchall()

    connection.close()

    return render_template(
        "admin_dashboard.html",

        total_messages=total_messages,
        new_messages=new_messages,
        read_messages=read_messages,
        replied_messages=replied_messages,

        recent_messages=recent_messages,
        notification_messages=notification_messages,

        total_activities=total_activities,
        total_logins=total_logins,
        total_replies=total_replies,
        recent_activities=recent_activities,

        sentiment_data=sentiment_data,
        dominant_sentiment=dominant_sentiment,
        dominant_sentiment_count=dominant_sentiment_count,

        priority_data=priority_data,
        dominant_priority=dominant_priority,
        dominant_priority_count=dominant_priority_count,

        reply_rate=reply_rate,
        handled_messages=handled_messages,
        handling_rate=handling_rate,

        intelligence_status=intelligence_status,
        intelligence_message=intelligence_message,

        message_trend=message_trend,
        trend_percentage=trend_percentage,

        recent_7_days=recent_7_days,
        previous_7_days=previous_7_days,

        peak_activity_day=peak_activity_day,
        peak_activity_count=peak_activity_count
    )

# =========================
# INTELLIGENCE OVERVIEW API
# =========================

@app.route("/admin/dashboard/intelligence/data")
@admin_required
def dashboard_intelligence_data():

    connection = get_db_connection()

    total_messages = connection.execute(
        """
        SELECT COUNT(*)
        FROM contacts
        """
    ).fetchone()[0]

    new_messages = connection.execute(
        """
        SELECT COUNT(*)
        FROM contacts
        WHERE status = 'New'
        """
    ).fetchone()[0]

    read_messages = connection.execute(
        """
        SELECT COUNT(*)
        FROM contacts
        WHERE status = 'Read'
        """
    ).fetchone()[0]

    replied_messages = connection.execute(
        """
        SELECT COUNT(*)
        FROM contacts
        WHERE status = 'Replied'
        """
    ).fetchone()[0]

    # Sentiment

    sentiment_data = connection.execute(
        """
        SELECT sentiment, COUNT(*) AS total
        FROM contacts
        WHERE sentiment IS NOT NULL
        AND sentiment != ''
        GROUP BY sentiment
        ORDER BY total DESC
        """
    ).fetchall()

    # Priority

    priority_data = connection.execute(
        """
        SELECT priority, COUNT(*) AS total
        FROM contacts
        WHERE priority IS NOT NULL
        AND priority != ''
        GROUP BY priority
        ORDER BY total DESC
        """
    ).fetchall()


        # -------------------------
    # MESSAGE TREND
    # -------------------------

    recent_7_days = connection.execute(
        """
        SELECT COUNT(*)
        FROM contacts
        WHERE datetime(created_at) >= datetime('now', '-7 days')
        """
    ).fetchone()[0]

    previous_7_days = connection.execute(
        """
        SELECT COUNT(*)
        FROM contacts
        WHERE datetime(created_at) >= datetime('now', '-14 days')
        AND datetime(created_at) < datetime('now', '-7 days')
        """
    ).fetchone()[0]

    if previous_7_days == 0:

        if recent_7_days > 0:
            message_trend = "Increasing"
        else:
            message_trend = "Stable"

        trend_percentage = 0

    else:

        trend_percentage = round(
            (
                (recent_7_days - previous_7_days)
                / previous_7_days
            ) * 100,
            1
        )

        if trend_percentage > 0:
            message_trend = "Increasing"

        elif trend_percentage < 0:
            message_trend = "Decreasing"

        else:
            message_trend = "Stable"


    # -------------------------
    # PEAK ACTIVITY
    # -------------------------

    peak_activity = connection.execute(
        """
        SELECT
            strftime('%w', created_at) AS day_number,
            COUNT(*) AS total
        FROM contacts
        GROUP BY day_number
        ORDER BY total DESC
        LIMIT 1
        """
    ).fetchone()


    day_names = {
        "0": "Sunday",
        "1": "Monday",
        "2": "Tuesday",
        "3": "Wednesday",
        "4": "Thursday",
        "5": "Friday",
        "6": "Saturday"
    }


    if peak_activity:

        peak_activity_day = day_names.get(
            peak_activity["day_number"],
            "Unknown"
        )

        peak_activity_count = peak_activity["total"]

    else:

        peak_activity_day = "No Data"
        peak_activity_count = 0

    connection.close()

    dominant_sentiment = (
        sentiment_data[0]["sentiment"]
        if sentiment_data
        else "No Data"
    )

    dominant_sentiment_count = (
        sentiment_data[0]["total"]
        if sentiment_data
        else 0
    )

    dominant_priority = (
        priority_data[0]["priority"]
        if priority_data
        else "No Data"
    )

    dominant_priority_count = (
        priority_data[0]["total"]
        if priority_data
        else 0
    )

    if total_messages > 0:

        reply_rate = round(
            (replied_messages / total_messages) * 100,
            1
        )

        handled_messages = (
            read_messages +
            replied_messages
        )

        handling_rate = round(
            (handled_messages / total_messages) * 100,
            1
        )

    else:

        reply_rate = 0
        handled_messages = 0
        handling_rate = 0

            # -------------------------
    # SMART RECOMMENDATION
    # -------------------------

    if total_messages == 0:

        intelligence_status = "No Data"

        intelligence_message = (
            "There is not enough message data to generate "
            "an intelligent recommendation."
        )

    elif new_messages >= 3:

        intelligence_status = "Needs Attention"

        intelligence_message = (
            f"You currently have {new_messages} new messages "
            "waiting for attention. Prioritize these messages "
            "to improve response performance."
        )

    elif reply_rate < 50:

        intelligence_status = "Needs Attention"

        intelligence_message = (
            f"Your reply rate is {reply_rate}%. "
            "Consider responding to pending messages more quickly "
            "to improve overall engagement."
        )

    elif trend_percentage > 20:

        intelligence_status = "High Activity"

        intelligence_message = (
            f"Message activity has increased by "
            f"{trend_percentage}% compared with the previous "
            "7 days. Consider monitoring incoming messages closely."
        )

    elif dominant_priority.lower() == "high":

        intelligence_status = "Priority Alert"

        intelligence_message = (
            "High-priority messages are currently dominant. "
            "Review priority messages first to maintain fast response times."
        )

    elif dominant_sentiment.lower() == "negative":

        intelligence_status = "Sentiment Alert"

        intelligence_message = (
            "Negative sentiment is currently dominant. "
            "Consider reviewing these conversations carefully "
            "and responding professionally."
        )

    elif reply_rate >= 80:

        intelligence_status = "Excellent"

        intelligence_message = (
            f"Your reply rate is {reply_rate}%. "
            "Message response performance is excellent."
        )

    elif handling_rate >= 80:

        intelligence_status = "Good"

        intelligence_message = (
            f"You have handled {handling_rate}% of your messages. "
            "Overall message management is performing well."
        )

    else:

        intelligence_status = "Good"

        intelligence_message = (
            "Message activity is stable. Continue monitoring "
            "new messages and maintaining consistent response times."
        )

    return {
        "total_messages": total_messages,
        "new_messages": new_messages,
        "read_messages": read_messages,
        "replied_messages": replied_messages,

        "dominant_sentiment": dominant_sentiment,
        "dominant_sentiment_count": dominant_sentiment_count,

        "sentiment_data": [
    {
        "sentiment": row["sentiment"],
        "total": row["total"]
    }
    for row in sentiment_data
    ],

        "dominant_priority": dominant_priority,
        "dominant_priority_count": dominant_priority_count,

        "priority_data": [
    {
        "priority": row["priority"],
        "total": row["total"]
    }
    for row in priority_data
],

        "reply_rate": reply_rate,
        "handled_messages": handled_messages,
        "handling_rate": handling_rate,

        "message_trend": message_trend,
        "trend_percentage": trend_percentage,

        "recent_7_days": recent_7_days,
        "previous_7_days": previous_7_days,

        "peak_activity_day": peak_activity_day,
        "peak_activity_count": peak_activity_count,

        "intelligence_status": intelligence_status,
        "intelligence_message": intelligence_message
    }


# =========================
# ADVANCED ANALYTICS API
# =========================

@app.route("/admin/dashboard/advanced-analytics/data")
@admin_required
def advanced_analytics_data():

    connection = get_db_connection()

    # -------------------------
    # TOTAL MESSAGES
    # -------------------------

    total_messages = connection.execute(
        """
        SELECT COUNT(*)
        FROM contacts
        """
    ).fetchone()[0]

    # -------------------------
    # UNIQUE SENDERS
    # -------------------------

    unique_senders = connection.execute(
        """
        SELECT COUNT(DISTINCT email)
        FROM contacts
        """
    ).fetchone()[0]

    # -------------------------
    # ACTIVE DAYS
    # -------------------------

    active_days = connection.execute(
        """
        SELECT COUNT(DISTINCT DATE(created_at))
        FROM contacts
        """
    ).fetchone()[0]

    # -------------------------
    # AVERAGE MESSAGES / DAY
    # -------------------------

    if active_days > 0:

        average_messages = round(
            total_messages / active_days,
            1
        )

    else:

        average_messages = 0

    # -------------------------
    # RECENT 7 DAYS
    # -------------------------

    recent_7_days = connection.execute(
        """
        SELECT COUNT(*)
        FROM contacts
        WHERE datetime(created_at)
        >= datetime('now', '-7 days')
        """
    ).fetchone()[0]

    # -------------------------
    # PREVIOUS 7 DAYS
    # -------------------------

    previous_7_days = connection.execute(
        """
        SELECT COUNT(*)
        FROM contacts
        WHERE datetime(created_at)
        >= datetime('now', '-14 days')

        AND datetime(created_at)
        < datetime('now', '-7 days')
        """
    ).fetchone()[0]

    # -------------------------
    # GROWTH
    # -------------------------

    if previous_7_days > 0:

        growth_percentage = round(
            (
                (recent_7_days - previous_7_days)
                / previous_7_days
            ) * 100,
            1
        )

    else:

        growth_percentage = 0

    connection.close()

    return {
        "total_messages": total_messages,
        "unique_senders": unique_senders,
        "active_days": active_days,
        "average_messages": average_messages,
        "recent_7_days": recent_7_days,
        "previous_7_days": previous_7_days,
        "growth_percentage": growth_percentage
    }

# =========================
# ADMIN MESSAGES
# =========================

@app.route("/admin/messages")
@admin_required
def admin_messages():

    search = request.args.get(
        "search",
        ""
    ).strip()

    status_filter = request.args.get(
        "status",
        ""
    ).strip()
    response_filter = request.args.get(
    "response",
    ""
    ).strip()
    # =========================
    # INTELLIGENCE FILTERS
    # =========================

    priority_filter = request.args.get(
        "priority",
        ""
    ).strip()

    sentiment_filter = request.args.get(
        "sentiment",
        ""
    ).strip()

    category_filter = request.args.get(
        "category",
        ""
    ).strip()

    # =========================
    # PAGINATION
    # =========================

    page = request.args.get(
        "page",
        1,
        type=int
    )

    if page < 1:
        page = 1

    per_page = 10

    offset = (page - 1) * per_page

    connection = get_db_connection()

    # =========================
    # BASE QUERY
    # =========================

    query = """
        SELECT *
        FROM contacts
        WHERE 1 = 1
    """

    parameters = []

    # =========================
    # SEARCH
    # =========================

    if search:

        query += """
            AND (
                name LIKE ?
                OR email LIKE ?
                OR message LIKE ?
            )
        """

        search_value = f"%{search}%"

        parameters.extend([
            search_value,
            search_value,
            search_value
        ])



# =========================
# STATUS FILTER
# =========================

    if status_filter.lower() == "pending":

        query += """
            AND status != 'Replied'
        """

    elif status_filter in [
        "New",
        "Read",
        "Replied"
    ]:

        query += """
            AND status = ?
        """

        parameters.append(
            status_filter
        )

    # =========================
    # RESPONSE FILTER
    # =========================

    if response_filter == "slow":

        query += """
            AND status != 'Replied'
        """

    # =========================
    # RESPONSE TIME FILTER
    # =========================

    if response_filter == "slow":

        query += """
            AND (
                (
                    status = 'Replied'
                    AND replied_at IS NOT NULL
                    AND (
                        (julianday(replied_at) -
                         julianday(created_at)) * 86400
                    ) > 14400
                )
                OR
                (
                    status != 'Replied'
                    AND (
                        (julianday('now') -
                         julianday(created_at)) * 86400
                    ) > 14400
                )
            )
        """

    # =========================
    # PRIORITY FILTER
    # =========================

    if priority_filter in [
        "High",
        "Medium",
        "Low"
    ]:

        query += """
            AND priority = ?
        """

        parameters.append(
            priority_filter
        )

    # =========================
    # SENTIMENT FILTER
    # =========================

    if sentiment_filter in [
        "Positive",
        "Neutral",
        "Negative"
    ]:

        query += """
            AND sentiment = ?
        """

        parameters.append(
            sentiment_filter
        )

    # =========================
    # CATEGORY FILTER
    # =========================

    if category_filter in [
        "Development",
        "Business",
        "Collaboration",
        "Support",
        "General"
    ]:

        query += """
            AND category = ?
        """

        parameters.append(
            category_filter
        )

    # =========================
    # TOTAL FILTERED MESSAGES
    # =========================

    count_query = query.replace(
        "SELECT *",
        "SELECT COUNT(*)"
    )

    total_filtered = connection.execute(
        count_query,
        parameters
    ).fetchone()[0]

    total_pages = max(
        1,
        (total_filtered + per_page - 1)
        // per_page
    )

    if page > total_pages:

        page = total_pages

        offset = (page - 1) * per_page

    # =========================
    # GET MESSAGES
    # =========================

    query += """
        ORDER BY created_at DESC
        LIMIT ?
        OFFSET ?
    """

    message_parameters = parameters + [
        per_page,
        offset
    ]

    messages = connection.execute(
        query,
        message_parameters
    ).fetchall()

    # =========================
    # DASHBOARD STATISTICS
    # =========================

    total_messages = connection.execute(
        """
        SELECT COUNT(*)
        FROM contacts
        """
    ).fetchone()[0]

    new_messages = connection.execute(
        """
        SELECT COUNT(*)
        FROM contacts
        WHERE status = 'New'
        """
    ).fetchone()[0]

    read_messages = connection.execute(
        """
        SELECT COUNT(*)
        FROM contacts
        WHERE status = 'Read'
        """
    ).fetchone()[0]

    replied_messages = connection.execute(
        """
        SELECT COUNT(*)
        FROM contacts
        WHERE status = 'Replied'
        """
    ).fetchone()[0]

    connection.close()

    return render_template(
        "admin_messages.html",

        messages=messages,

        total_messages=total_messages,
        new_messages=new_messages,
        read_messages=read_messages,
        replied_messages=replied_messages,

        search=search,
        status_filter=status_filter,

        priority_filter=priority_filter,
        sentiment_filter=sentiment_filter,
        category_filter=category_filter,

        page=page,
        per_page=per_page,
        total_filtered=total_filtered,
        total_pages=total_pages
    )


# =========================
# MESSAGE INTELLIGENCE ANALYTICS
# =========================

@app.route("/admin/dashboard/intelligence")
@admin_required
def intelligence_analytics():

    connection = get_db_connection()

    total_messages = connection.execute(
        """
        SELECT COUNT(*)
        FROM contacts
        WHERE intelligence_score IS NOT NULL
        """
    ).fetchone()[0]

    average_score = connection.execute(
        """
        SELECT AVG(intelligence_score)
        FROM contacts
        WHERE intelligence_score IS NOT NULL
        """
    ).fetchone()[0]

    if average_score is None:
        average_score = 0
    else:
        average_score = round(average_score, 1)

    high_priority = connection.execute(
        """
        SELECT COUNT(*)
        FROM contacts
        WHERE priority = 'High'
        """
    ).fetchone()[0]

    negative_sentiment = connection.execute(
        """
        SELECT COUNT(*)
        FROM contacts
        WHERE sentiment = 'Negative'
        """
    ).fetchone()[0]

    top_category = connection.execute(
        """
        SELECT category, COUNT(*) AS total
        FROM contacts
        GROUP BY category
        ORDER BY total DESC
        LIMIT 1
        """
    ).fetchone()

    if top_category:
        top_category_name = top_category["category"]
        top_category_count = top_category["total"]
    else:
        top_category_name = "N/A"
        top_category_count = 0

    sentiment_data = connection.execute(
        """
        SELECT sentiment, COUNT(*) AS total
        FROM contacts
        GROUP BY sentiment
        ORDER BY total DESC
        """
    ).fetchall()

    priority_data = connection.execute(
        """
        SELECT priority, COUNT(*) AS total
        FROM contacts
        GROUP BY priority
        ORDER BY total DESC
        """
    ).fetchall()

    connection.close()

    return render_template(
        "intelligence_analytics.html",

        total_messages=total_messages,
        average_score=average_score,

        high_priority=high_priority,
        negative_sentiment=negative_sentiment,

        top_category_name=top_category_name,
        top_category_count=top_category_count,

        sentiment_data=sentiment_data,
        priority_data=priority_data
    )

# =========================
# VIEW SINGLE MESSAGE
# =========================

@app.route("/admin/messages/<int:message_id>")
@admin_required
def view_message(message_id):

    connection = get_db_connection()

    message = connection.execute(
        """
        SELECT *
        FROM contacts
        WHERE id = ?
        """,
        (message_id,)
    ).fetchone()

    if message is None:
        connection.close()
        return "Message not found.", 404

    # Automatically mark New messages as Read
    if message["status"] == "New":

        connection.execute(
            """
            UPDATE contacts
            SET status = 'Read'
            WHERE id = ?
            """,
            (message_id,)
        )

        connection.commit()

        # Fetch updated message
        message = connection.execute(
            """
            SELECT *
            FROM contacts
            WHERE id = ?
            """,
            (message_id,)
        ).fetchone()

    connection.close()

    # =========================
    # ACTIVITY LOG
    # =========================

    log_activity(
        "Read Message",
        f"Admin viewed message from {message['name']}",
        message_id
    )

    return render_template(
        "admin_message.html",
        message=message
    )

# =========================
# MARK NOTIFICATION AS READ
# =========================

@app.route("/admin/notifications/<int:message_id>/read", methods=["POST"])
@admin_required
def mark_notification_read(message_id):

    connection = get_db_connection()

    message = connection.execute(
        """
        SELECT *
        FROM contacts
        WHERE id = ?
        """,
        (message_id,)
    ).fetchone()

    if message is None:
        connection.close()

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return {
                "success": False,
                "message": "Message not found."
            }, 404

        flash("Message not found.", "error")
        return redirect(url_for("admin_dashboard"))

    was_new = message["status"] == "New"

    if was_new:

        connection.execute(
            """
            UPDATE contacts
            SET status = 'Read'
            WHERE id = ?
            """,
            (message_id,)
        )

        connection.commit()

        log_activity(
            "Notification Read",
            f"Admin marked notification from {message['name']} as read",
            message_id
        )

    connection.close()

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":

        connection = get_db_connection()

        remaining_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM contacts
            WHERE status = 'New'
            """
        ).fetchone()[0]

        connection.close()

        return {
            "success": True,
            "count": remaining_count,
            "message_id": message_id
        }

    return redirect(url_for("admin_dashboard"))

# =========================
# MARK ALL NOTIFICATION AS READ
# =========================
@app.route("/admin/notifications/mark-all-read", methods=["POST"])
@admin_required
def mark_all_notifications_read():

    connection = get_db_connection()

    unread_messages = connection.execute(
        """
        SELECT COUNT(*)
        FROM contacts
        WHERE status = 'New'
        """
    ).fetchone()[0]

    connection.execute(
        """
        UPDATE contacts
        SET status = 'Read'
        WHERE status = 'New'
        """
    )

    connection.commit()
    connection.close()

    if unread_messages > 0:

        log_activity(
            "Notifications Marked Read",
            f"Admin marked {unread_messages} notifications as read"
        )

    # AJAX request
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":

        return {
            "success": True,
            "count": 0,
            "message": f"{unread_messages} notifications marked as read."
        }

    # Normal request fallback
    if unread_messages > 0:

        flash(
            f"{unread_messages} messages marked as read.",
            "success"
        )

    else:

        flash(
            "There are no new messages.",
            "success"
        )

    return redirect(url_for("admin_dashboard"))

@app.route("/admin/notifications/data")
@admin_required
def notification_data():

    connection = get_db_connection()

    notifications = connection.execute(
        """
        SELECT id, name, email, created_at
        FROM contacts
        WHERE status = 'New'
        ORDER BY created_at DESC
        """
    ).fetchall()

    connection.close()

    return {
        "count": len(notifications),
        "notifications": [
            {
                "id": message["id"],
                "name": message["name"],
                "email": message["email"],
                "created_at": message["created_at"]
            }
            for message in notifications
        ]
    }

@app.route("/admin/notifications/data")
@admin_required
def notifications_data():

    connection = get_db_connection()

    notifications = connection.execute(
        """
        SELECT
            id,
            message,
            message_id,
            is_read,
            created_at
        FROM notifications
        ORDER BY created_at DESC
        LIMIT 10
        """
    ).fetchall()

    unread_count = connection.execute(
        """
        SELECT COUNT(*)
        FROM notifications
        WHERE is_read = 0
        """
    ).fetchone()[0]

    connection.close()

    return {
        "notifications": [
            {
                "id": notification["id"],
                "message": notification["message"],
                "message_id": notification["message_id"],
                "is_read": notification["is_read"],
                "created_at": notification["created_at"]
            }
            for notification in notifications
        ],
        "unread_count": unread_count
    }

@app.route("/admin/recent-messages/data")
@admin_required
def recent_messages_data():

    connection = get_db_connection()

    messages = connection.execute(
        """
        SELECT id, name, email, status, created_at
        FROM contacts
        ORDER BY created_at DESC
        LIMIT 5
        """
    ).fetchall()

    connection.close()

    return {
        "messages": [
            {
                "id": message["id"],
                "name": message["name"],
                "email": message["email"],
                "status": message["status"],
                "created_at": message["created_at"]
            }
            for message in messages
        ]
    }

@app.route("/admin/recent-activity/data")
@admin_required
def recent_activity_data():

    connection = get_db_connection()

    activities = connection.execute(
        """
        SELECT id, action, description, message_id, created_at
        FROM activity_logs
        ORDER BY created_at DESC
        LIMIT 5
        """
    ).fetchall()

    connection.close()

    return {
        "activities": [
            {
                "id": activity["id"],
                "action": activity["action"],
                "description": activity["description"],
                "message_id": activity["message_id"],
                "created_at": activity["created_at"]
            }
            for activity in activities
        ]
    }


@app.route("/admin/dashboard/stats")
@admin_required
def dashboard_stats():

    connection = get_db_connection()

    # =========================
    # MESSAGE STATISTICS
    # =========================

    total_messages = connection.execute(
        "SELECT COUNT(*) FROM contacts"
    ).fetchone()[0]

    new_messages = connection.execute(
        "SELECT COUNT(*) FROM contacts WHERE status = 'New'"
    ).fetchone()[0]

    read_messages = connection.execute(
        "SELECT COUNT(*) FROM contacts WHERE status = 'Read'"
    ).fetchone()[0]

    replied_messages = connection.execute(
        "SELECT COUNT(*) FROM contacts WHERE status = 'Replied'"
    ).fetchone()[0]


    # =========================
    # PENDING REPLIES
    # =========================

    pending_replies = connection.execute(
        """
        SELECT COUNT(*)
        FROM contacts
        WHERE status != 'Replied'
        """
    ).fetchone()[0]


    # =========================
    # ACTIVITY ANALYTICS
    # =========================

    total_activities = connection.execute(
        "SELECT COUNT(*) FROM activity_logs"
    ).fetchone()[0]

    total_logins = connection.execute(
        """
        SELECT COUNT(*)
        FROM activity_logs
        WHERE action = 'Login'
        """
    ).fetchone()[0]

    total_replies = connection.execute(
        """
        SELECT COUNT(*)
        FROM activity_logs
        WHERE action = 'Reply Sent'
        """
    ).fetchone()[0]

    connection.close()

    return {
        "total_messages": total_messages,
        "new_messages": new_messages,
        "read_messages": read_messages,
        "replied_messages": replied_messages,
        "pending_replies": pending_replies,
        "total_activities": total_activities,
        "total_logins": total_logins,
        "total_replies": total_replies,
    }
# =========================
# ADVANCED MESSAGE INSIGHTS
# =========================

@app.route("/admin/dashboard/advanced-insights")
@admin_required
def advanced_message_insights():

    connection = get_db_connection()
    cursor = connection.cursor()

    # Total messages
    cursor.execute("""
        SELECT COUNT(*)
        FROM contacts
    """)
    total_messages = cursor.fetchone()[0]

    # Unique senders
    cursor.execute("""
        SELECT COUNT(DISTINCT email)
        FROM contacts
    """)
    unique_senders = cursor.fetchone()[0]

        # Repeat senders
    cursor.execute("""
        SELECT COUNT(*)
        FROM (
            SELECT email
            FROM contacts
            WHERE email IS NOT NULL
            AND TRIM(email) != ''
            GROUP BY email
            HAVING COUNT(*) > 1
        )
    """)

    repeat_senders = cursor.fetchone()[0]

    # Replied messages
    cursor.execute("""
        SELECT COUNT(*)
        FROM contacts
        WHERE status = 'Replied'
    """)
    replied_messages = cursor.fetchone()[0]

    # Unreplied messages
    cursor.execute("""
        SELECT COUNT(*)
        FROM contacts
        WHERE status != 'Replied'
    """)
    unreplied_messages = cursor.fetchone()[0]

    # Response rate
    if total_messages > 0:
        response_rate = round(
            (replied_messages / total_messages) * 100,
            2
        )
    else:
        response_rate = 0

    # Average message length
    cursor.execute("""
        SELECT AVG(LENGTH(message))
        FROM contacts
    """)

    average_message_length = cursor.fetchone()[0] or 0

    average_message_length = round(
        average_message_length,
        2
    )

    connection.close()

    return {
        "total_messages": total_messages,
        "unique_senders": unique_senders,
        "repeat_senders": repeat_senders,
        "replied_messages": replied_messages,
        "unreplied_messages": unreplied_messages,
        "response_rate": response_rate,
        "average_message_length": average_message_length
    }

# =========================
# MESSAGE PERFORMANCE INSIGHTS
# =========================

@app.route("/admin/dashboard/message-performance")
@admin_required
def message_performance_insights():

    connection = get_db_connection()
    cursor = connection.cursor()


    # =========================
    # MESSAGE PERFORMANCE DATE FILTER
    # =========================

    from datetime import datetime, timedelta

    date_range = request.args.get("range", "all")

    allowed_ranges = ["7", "30", "90", "all"]

    if date_range not in allowed_ranges:
        date_range = "all"

    date_condition = ""
    query_params = []

    if date_range in ["7", "30", "90"]:

        days = int(date_range)

        start_date = (
            datetime.now() - timedelta(days=days)
        ).strftime("%Y-%m-%d")

        date_condition = " AND created_at >= ? "
        query_params.append(start_date)

    # =========================
    # TOTAL MESSAGES
    # =========================

    cursor.execute(
    "SELECT COUNT(*) FROM contacts WHERE 1=1"
    + date_condition,
    query_params
)

    total_messages = cursor.fetchone()[0]

    # =========================
    # TOTAL REPLIED
    # =========================

    cursor.execute(
    "SELECT COUNT(*) FROM contacts "
    "WHERE status = 'Replied'"
    + date_condition,
    query_params
)

    total_replied = cursor.fetchone()[0]

    # =========================
    # TOTAL READ
    # =========================

    cursor.execute(
    "SELECT COUNT(*) FROM contacts "
    "WHERE status = 'Read'"
    + date_condition,
    query_params
)

    total_read = cursor.fetchone()[0]

    # =========================
    # TOTAL NEW
    # =========================

    cursor.execute(
    "SELECT COUNT(*) FROM contacts "
    "WHERE status = 'New'"
    + date_condition,
    query_params
)

    total_new = cursor.fetchone()[0]

    # =========================
    # UNIQUE SENDERS
    # =========================

    cursor.execute(
    "SELECT COUNT(DISTINCT email) FROM contacts "
    "WHERE 1=1"
    + date_condition,
    query_params
)

    unique_senders = cursor.fetchone()[0]

    # =========================
    # REPLY RATE
    # =========================

    if total_messages > 0:
        reply_rate = round(
            (total_replied / total_messages) * 100,
            2
        )
    else:
        reply_rate = 0

    # =========================
    # READ RATE
    # =========================

    if total_messages > 0:
        read_rate = round(
            ((total_read + total_replied) / total_messages) * 100,
            2
        )
    else:
        read_rate = 0

    # =========================
    # NEW MESSAGE RATE
    # =========================

    if total_messages > 0:
        new_rate = round(
            (total_new / total_messages) * 100,
            2
        )
    else:
        new_rate = 0

        # =========================
    # DAILY MESSAGE VOLUME
    # =========================

    cursor.execute(
    """
    SELECT
        DATE(created_at) AS message_date,
        COUNT(*) AS message_count
    FROM contacts
    WHERE 1=1
    """
    + date_condition +
    """
    GROUP BY DATE(created_at)
    ORDER BY DATE(created_at)
    """,
    query_params
)

    message_volume = cursor.fetchall()

        # =========================
    # PEAK MESSAGING TIME
    # =========================

    cursor.execute(
    """
    SELECT
        strftime('%H', created_at) AS message_hour,
        COUNT(*) AS message_count
    FROM contacts
    WHERE 1=1
    """
    + date_condition +
    """
    GROUP BY strftime('%H', created_at)
    ORDER BY message_count DESC
    LIMIT 1
    """,
    query_params
)

    peak_time_data = cursor.fetchone()

    if peak_time_data:
        peak_messaging_hour = peak_time_data["message_hour"]
        peak_messaging_count = peak_time_data["message_count"]
    else:
        peak_messaging_hour = None
        peak_messaging_count = 0

        # =========================
    # BEST MESSAGING DAY
    # =========================

    cursor.execute(
    """
    SELECT
        CASE strftime('%w', created_at)
            WHEN '0' THEN 'Sunday'
            WHEN '1' THEN 'Monday'
            WHEN '2' THEN 'Tuesday'
            WHEN '3' THEN 'Wednesday'
            WHEN '4' THEN 'Thursday'
            WHEN '5' THEN 'Friday'
            WHEN '6' THEN 'Saturday'
        END AS message_day,
        COUNT(*) AS message_count
    FROM contacts
    WHERE 1=1
    """
    + date_condition +
    """
    GROUP BY strftime('%w', created_at)
    ORDER BY message_count DESC
    LIMIT 1
    """,
    query_params
)

    best_day_data = cursor.fetchone()

    if best_day_data:
        best_messaging_day = best_day_data["message_day"]
        best_messaging_day_count = best_day_data["message_count"]
    else:
        best_messaging_day = None
        best_messaging_day_count = 0


        # =========================
    # REPLY PERFORMANCE
    # =========================

    unreplied_messages = total_messages - total_replied

    if total_messages > 0:
        response_coverage = round(
            (total_replied / total_messages) * 100,
            2
        )
    else:
        response_coverage = 0

    # =========================
    # RESPONSE TIME ANALYSIS
    # =========================

    cursor.execute(
    """
    SELECT AVG(
        (julianday(replied_at) - julianday(created_at)) * 86400
    )
    FROM contacts
    WHERE replied_at IS NOT NULL
    """
    + date_condition,
    query_params
)

    average_response_seconds = cursor.fetchone()[0]

    if average_response_seconds:
        average_response_seconds = round(
            average_response_seconds
        )
    else:
        average_response_seconds = 0

    # FASTEST RESPONSE
    cursor.execute(
    """
    SELECT MIN(
        (julianday(replied_at) - julianday(created_at)) * 86400
    )
    FROM contacts
    WHERE replied_at IS NOT NULL
    """
    + date_condition,
    query_params
)

    fastest_response_seconds = cursor.fetchone()[0]

    if fastest_response_seconds:
        fastest_response_seconds = round(
            fastest_response_seconds
        )
    else:
        fastest_response_seconds = 0

    # SLOWEST RESPONSE
    cursor.execute(
    """
    SELECT MAX(
        (julianday(replied_at) - julianday(created_at)) * 86400
    )
    FROM contacts
    WHERE replied_at IS NOT NULL
    """
    + date_condition,
    query_params
)

    slowest_response_seconds = cursor.fetchone()[0]

    if slowest_response_seconds:
        slowest_response_seconds = round(
            slowest_response_seconds
        )
    else:
        slowest_response_seconds = 0

        # =========================
    # RESPONSE TIME DISTRIBUTION
    # =========================


    cursor.execute(
        """
        SELECT
            CASE
                WHEN (
                    (julianday(replied_at) - julianday(created_at)) * 86400
                ) < 900 THEN 'Under 15 Minutes'

                WHEN (
                    (julianday(replied_at) - julianday(created_at)) * 86400
                ) < 3600 THEN '15-60 Minutes'

                WHEN (
                    (julianday(replied_at) - julianday(created_at)) * 86400
                ) < 14400 THEN '1-4 Hours'

                ELSE 'Over 4 Hours'
            END AS response_range,
            COUNT(*) AS response_count
        FROM contacts
        WHERE replied_at IS NOT NULL
        """
        + date_condition +
        """
        GROUP BY response_range
        ORDER BY
            CASE response_range
                WHEN 'Under 15 Minutes' THEN 1
                WHEN '15-60 Minutes' THEN 2
                WHEN '1-4 Hours' THEN 3
                WHEN 'Over 4 Hours' THEN 4
            END
        """,
        query_params
    )

    response_time_rows = cursor.fetchall()

    response_time_distribution = [
    {
        "response_range": row["response_range"],
        "response_count": row["response_count"]
    }
    for row in response_time_rows
]

        # =========================
    # RESPONSE TIME QUALITY SCORE
    # =========================


    cursor.execute(
        """
        SELECT
            (julianday(replied_at) - julianday(created_at)) * 86400
            AS response_seconds
        FROM contacts
        WHERE replied_at IS NOT NULL
        """
        + date_condition,
        query_params
    )

    response_quality_rows = cursor.fetchall()

    total_quality_score = 0
    quality_response_count = 0

    for row in response_quality_rows:

        response_seconds = row["response_seconds"]

        if response_seconds <= 900:
            score = 100

        elif response_seconds <= 1800:
            score = 90

        elif response_seconds <= 3600:
            score = 80

        elif response_seconds <= 7200:
            score = 70

        elif response_seconds <= 14400:
            score = 60

        elif response_seconds <= 28800:
            score = 45

        elif response_seconds <= 86400:
            score = 30

        else:
            score = 15

        total_quality_score += score
        quality_response_count += 1

    if quality_response_count > 0:

        response_time_quality_score = round(
            total_quality_score / quality_response_count,
            2
        )

    else:

        response_time_quality_score = 0


    # =========================
    # QUALITY RATING
    # =========================

    if response_time_quality_score >= 90:

        response_quality_rating = "Excellent"

    elif response_time_quality_score >= 75:

        response_quality_rating = "Good"

    elif response_time_quality_score >= 50:

        response_quality_rating = "Average"

    elif response_time_quality_score > 0:

        response_quality_rating = "Poor"

    else:

        response_quality_rating = "No Data"

    # =========================
# RESPONSE QUALITY TARGET
# =========================

    response_quality_target = 80

    response_quality_difference = round(
    response_time_quality_score - response_quality_target,
    2
)

    if response_quality_difference >= 0:
        response_quality_target_status = "On Target"
    else:
        response_quality_target_status = "Below Target"

# =========================
# RESPONSE QUALITY RECOMMENDATION
# =========================

    if response_time_quality_score >= 90:

        response_quality_recommendation = (
        "Excellent performance. "
        "Maintain your current response speed."
    )

    elif response_time_quality_score >= 75:

        response_quality_recommendation = (
        "Good performance. "
        "Reduce response times slightly to reach the excellent range."
    )

    elif response_time_quality_score >= 50:

        response_quality_recommendation = (
        "Average performance. "
        "Focus on reducing slower responses, especially those above 4 hours."
    )

    elif response_time_quality_score > 0:

        response_quality_recommendation = (
        "Poor performance. "
        "Prioritize faster replies to significantly improve response quality."
    )

    else:

        response_quality_recommendation = (
        "No response data available. "
        "Reply to messages to start measuring response quality."
    )

    # =========================
# RESPONSE QUALITY GOAL PROGRESS
# =========================

    if response_quality_target > 0:

        response_quality_goal_progress = round(
        (
            response_time_quality_score
            / response_quality_target
        ) * 100,
        2
    )

    else:

        response_quality_goal_progress = 0

# Keep progress within 0-100%

    response_quality_goal_progress = min(
    max(response_quality_goal_progress, 0),
    100
)

        # =========================
    # RESPONSE QUALITY INSIGHT
    # =========================

    if response_time_quality_score >= 90:

        response_quality_insight = (
            "Excellent response performance. "
            "Most messages are being handled very quickly."
        )

    elif response_time_quality_score >= 75:

        response_quality_insight = (
            "Good response performance. "
            "Most messages are receiving timely responses."
        )

    elif response_time_quality_score >= 50:

        response_quality_insight = (
            "Average response performance. "
            "Response times could be improved."
        )

    elif response_time_quality_score > 0:

        response_quality_insight = (
            "Poor response performance. "
            "Messages are taking too long to receive a reply."
        )

    else:

        response_quality_insight = (
            "No response data available yet."
        )

        # =========================
    # RESPONSE QUALITY BREAKDOWN
    # =========================


    cursor.execute(
        """
        SELECT
            SUM(
                CASE
                    WHEN (
                        (julianday(replied_at) - julianday(created_at)) * 86400
                    ) <= 3600 THEN 1
                    ELSE 0
                END
            ) AS fast_responses,

            SUM(
                CASE
                    WHEN (
                        (julianday(replied_at) - julianday(created_at)) * 86400
                    ) > 3600
                    AND (
                        (julianday(replied_at) - julianday(created_at)) * 86400
                    ) <= 14400 THEN 1
                    ELSE 0
                END
            ) AS moderate_responses,

            SUM(
                CASE
                    WHEN (
                        (julianday(replied_at) - julianday(created_at)) * 86400
                    ) > 14400 THEN 1
                    ELSE 0
                END
            ) AS slow_responses

        FROM contacts
        WHERE replied_at IS NOT NULL
        """
        + date_condition,
        query_params
    )

    response_quality_breakdown = cursor.fetchone()

    fast_responses = response_quality_breakdown["fast_responses"] or 0
    moderate_responses = response_quality_breakdown["moderate_responses"] or 0
    slow_responses = response_quality_breakdown["slow_responses"] or 0

    # =========================
    # DAILY RESPONSE QUALITY TREND
    # =========================


    cursor.execute(
        """
        SELECT
            DATE(created_at) AS response_date,
            AVG(
                CASE
                    WHEN (
                        (julianday(replied_at) - julianday(created_at)) * 86400
                    ) <= 900 THEN 100

                    WHEN (
                        (julianday(replied_at) - julianday(created_at)) * 86400
                    ) <= 1800 THEN 90

                    WHEN (
                        (julianday(replied_at) - julianday(created_at)) * 86400
                    ) <= 3600 THEN 80

                    WHEN (
                        (julianday(replied_at) - julianday(created_at)) * 86400
                    ) <= 7200 THEN 70

                    WHEN (
                        (julianday(replied_at) - julianday(created_at)) * 86400
                    ) <= 14400 THEN 60

                    WHEN (
                        (julianday(replied_at) - julianday(created_at)) * 86400
                    ) <= 28800 THEN 45

                    WHEN (
                        (julianday(replied_at) - julianday(created_at)) * 86400
                    ) <= 86400 THEN 30

                    ELSE 15
                END
            ) AS quality_score
        FROM contacts
        WHERE replied_at IS NOT NULL
        """
        + date_condition +
        """
        GROUP BY DATE(created_at)
        ORDER BY DATE(created_at)
        """,
        query_params
    )

    response_quality_trend_rows = cursor.fetchall()

    response_quality_trend = [
        {
            "date": row["response_date"],
            "score": round(row["quality_score"], 2)
        }
        for row in response_quality_trend_rows
    ]



    # =========================
    # QUALITY CHANGE COMPARISON
    # =========================

    current_quality_score = response_time_quality_score
    previous_quality_score = None
    quality_score_change = None

    if date_range in ["7", "30", "90"]:

        days = int(date_range)

        # Current period start date
        current_period_start = datetime.strptime(
            start_date, "%Y-%m-%d"
        )

        # Previous equal-length period
        previous_period_start = (
            current_period_start - timedelta(days=days)
        ).strftime("%Y-%m-%d")

        current_period_start_text = (
            current_period_start.strftime("%Y-%m-%d")
        )

        # Fetch responses from the previous period
        cursor.execute(
            """
            SELECT
                (julianday(replied_at) - julianday(created_at))
                * 86400 AS response_seconds
            FROM contacts
            WHERE replied_at IS NOT NULL
              AND created_at >= ?
              AND created_at < ?
            """,
            [
                previous_period_start,
                current_period_start_text
            ]
        )

        previous_quality_rows = cursor.fetchall()

        previous_total_score = 0
        previous_response_count = 0

        for row in previous_quality_rows:

            response_seconds = row["response_seconds"]

            if response_seconds is None:
                continue

            if response_seconds <= 900:
                score = 100
            elif response_seconds <= 1800:
                score = 90
            elif response_seconds <= 3600:
                score = 80
            elif response_seconds <= 7200:
                score = 70
            elif response_seconds <= 14400:
                score = 60
            elif response_seconds <= 28800:
                score = 45
            elif response_seconds <= 86400:
                score = 30
            else:
                score = 15

            previous_total_score += score
            previous_response_count += 1

        if previous_response_count > 0:

            previous_quality_score = round(
                previous_total_score / previous_response_count,
                2
            )

            quality_score_change = round(
                current_quality_score - previous_quality_score,
                2
            )

    # =========================
    # QUALITY CHANGE INSIGHT
    # =========================

    if quality_score_change is None:

        quality_change_direction = "Not enough data"

        if date_range == "all":
            quality_change_message = (
                "Select 7, 30, or 90 days to compare "
                "the current period with the previous period."
            )
        elif current_quality_score == 0:
            quality_change_message = (
                "No current-period response data is available."
            )
        else:
            quality_change_message = (
                "No previous-period response data is available "
                "for a reliable comparison."
            )

    elif quality_score_change > 0:

        quality_change_direction = "Improved"

        quality_change_message = (
            f"Response quality improved by "
            f"{quality_score_change} points "
            f"compared with the previous period."
        )

    elif quality_score_change < 0:

        quality_change_direction = "Declined"

        quality_change_message = (
            f"Response quality declined by "
            f"{abs(quality_score_change)} points "
            f"compared with the previous period."
        )

    else:

        quality_change_direction = "Stable"

        quality_change_message = (
            "Response quality remained stable "
            "compared with the previous period."
        )



    # =========================
    # SMART RESPONSE RECOMMENDATIONS
    # =========================

    response_quality_recommendations = []

    if response_time_quality_score >= 90:
        response_quality_recommendations.append(
            "Excellent response speed. Maintain your current performance."
        )

    elif response_time_quality_score >= 75:
        response_quality_recommendations.append(
            "Good response quality. Try to reply to messages even faster."
        )

    elif response_time_quality_score >= 50:
        response_quality_recommendations.append(
            "Response quality needs improvement. Prioritize pending messages."
        )

    else:
        response_quality_recommendations.append(
            "Focus on reducing response delays and replying to older messages first."
        )

    # Pending message recommendations
    if total_new > 0:
        response_quality_recommendations.append(
            f"You have {total_new} new messages. Review and respond to them promptly."
        )

    if unreplied_messages > 0:
        response_quality_recommendations.append(
            f"{unreplied_messages} messages have not been replied to. Review your pending workload."
        )

    # Slow response recommendations
    if slow_responses > 0:
        response_quality_recommendations.append(
            f"{slow_responses} slow responses detected. Identify causes of delays."
        )

    # Positive reinforcement
    if fast_responses > 0:
        response_quality_recommendations.append(
            f"{fast_responses} fast responses recorded. Use these as your performance target."
        )

    if not response_quality_recommendations:
        response_quality_recommendations.append(
            "More response data is needed to generate recommendations."
        )


    # =========================
    # RESPONSE PERFORMANCE ALERTS
    # =========================

    response_performance_alerts = []

    if total_new >= 5:
        response_performance_alerts.append({
            "level": "warning",
            "title": "Pending Messages Alert",
            "message": f"{total_new} new messages are waiting for review."
        })

    if slow_responses >= 0:
        response_performance_alerts.append({
            "level": "warning",
            "title": "Slow Response Alert",
            "message": f"{slow_responses} slow responses detected. Review response delays."
        })

    if response_time_quality_score < 50:
        response_performance_alerts.append({
            "level": "danger",
            "title": "Low Response Quality",
            "message": "Response quality is low. Prioritize faster replies."
        })

    if not response_performance_alerts:
        response_performance_alerts.append({
            "level": "success",
            "title": "Performance Status",
            "message": "No major response performance alerts detected."
        })
    # =========================
    # RESPONSE ALERT SUMMARY
    # =========================

    total_response_alerts = len(response_performance_alerts)

    warning_alerts_count = sum(
        1 for alert in response_performance_alerts
        if alert["level"] == "warning"
    )

    critical_alerts_count = sum(
        1 for alert in response_performance_alerts
        if alert["level"] == "danger"
    )

    healthy_alerts_count = sum(
        1 for alert in response_performance_alerts
        if alert["level"] == "success"
    )

    connection.close()

    return render_template(
        "message_performance.html",
        total_messages=total_messages,
        total_replied=total_replied,
        total_read=total_read,
        total_new=total_new,
        date_range=date_range,
        unique_senders=unique_senders,
        reply_rate=reply_rate,
        read_rate=read_rate,
        new_rate=new_rate,
        message_volume=message_volume,
        peak_messaging_hour=peak_messaging_hour,
        peak_messaging_count=peak_messaging_count,
        best_messaging_day=best_messaging_day,
        best_messaging_day_count=best_messaging_day_count,
        unreplied_messages=unreplied_messages,
        response_coverage=response_coverage,
        average_response_seconds=average_response_seconds,
        fastest_response_seconds=fastest_response_seconds,
        slowest_response_seconds=slowest_response_seconds,
        response_time_distribution=response_time_distribution,
        response_time_quality_score=response_time_quality_score,
        response_quality_rating=response_quality_rating,
        response_quality_target=response_quality_target,
        response_quality_difference=response_quality_difference,
        response_quality_target_status=response_quality_target_status,
        response_quality_goal_progress=response_quality_goal_progress,
        response_quality_recommendation=response_quality_recommendation,
        response_performance_alerts=response_performance_alerts,
        total_response_alerts=total_response_alerts,
        warning_alerts_count=warning_alerts_count,
        critical_alerts_count=critical_alerts_count,
        healthy_alerts_count=healthy_alerts_count,
        response_quality_insight=response_quality_insight,
        response_quality_trend=response_quality_trend,
        current_quality_score=current_quality_score,
        previous_quality_score=previous_quality_score,
        quality_score_change=quality_score_change,
        quality_change_direction=quality_change_direction,
        quality_change_message=quality_change_message,
        response_quality_recommendations=response_quality_recommendations,
        fast_responses=fast_responses,
        moderate_responses=moderate_responses,
        slow_responses=slow_responses
    )

# =========================
# MESSAGE GROWTH INSIGHTS
# =========================

@app.route("/admin/dashboard/message-growth")
@admin_required
def message_growth_insights():

    range_value = request.args.get("range", "7")

    if range_value not in ["7", "30", "90"]:
        range_value = "7"

    days = int(range_value)

    connection = get_db_connection()
    cursor = connection.cursor()

    # Current period
    cursor.execute("""
        SELECT COUNT(*)
        FROM contacts
        WHERE datetime(created_at) >= datetime('now', ? || ' days')
    """, (f"-{days}",))

    current_messages = cursor.fetchone()[0]

    # Previous period
    cursor.execute("""
        SELECT COUNT(*)
        FROM contacts
        WHERE datetime(created_at) >= datetime('now', ? || ' days')
        AND datetime(created_at) < datetime('now', ? || ' days')
    """, (f"-{days * 2}", f"-{days}"))

    previous_messages = cursor.fetchone()[0]

    # Growth percentage
    if previous_messages > 0:

        growth_percentage = round(
            (
                (current_messages - previous_messages)
                / previous_messages
            ) * 100,
            2
        )

    elif current_messages > 0:

        growth_percentage = 100

    else:

        growth_percentage = 0

    # Growth direction
    if growth_percentage > 0:

        direction = "up"

    elif growth_percentage < 0:

        direction = "down"

    else:

        direction = "stable"

    connection.close()

    return {
        "range_days": days,
        "current_messages": current_messages,
        "previous_messages": previous_messages,
        "growth_percentage": growth_percentage,
        "direction": direction
    }

# =========================
# PEAK ACTIVITY INSIGHTS
# =========================

@app.route("/admin/dashboard/peak-activity")
@admin_required
def peak_activity_insights():

    connection = get_db_connection()
    cursor = connection.cursor()

    # =========================
    # BUSIEST DAY
    # =========================

    cursor.execute("""
        SELECT
            DATE(created_at) AS message_date,
            COUNT(*) AS message_count
        FROM contacts
        GROUP BY DATE(created_at)
        ORDER BY message_count DESC
        LIMIT 1
    """)

    busiest_day = cursor.fetchone()

    if busiest_day:
        busiest_date = busiest_day["message_date"]
        busiest_day_count = busiest_day["message_count"]
    else:
        busiest_date = None
        busiest_day_count = 0

    # =========================
    # PEAK HOUR
    # =========================

    cursor.execute("""
        SELECT
            strftime('%H', created_at) AS message_hour,
            COUNT(*) AS message_count
        FROM contacts
        GROUP BY strftime('%H', created_at)
        ORDER BY message_count DESC
        LIMIT 1
    """)

    peak_hour = cursor.fetchone()

    if peak_hour:
        peak_hour_value = peak_hour["message_hour"]
        peak_hour_count = peak_hour["message_count"]
    else:
        peak_hour_value = None
        peak_hour_count = 0

    connection.close()

    return {
        "busiest_day": busiest_date,
        "busiest_day_count": busiest_day_count,
        "peak_hour": peak_hour_value,
        "peak_hour_count": peak_hour_count
    }

# =========================
# SENDER & MESSAGE BEHAVIOR
# =========================

@app.route("/admin/dashboard/message-behavior")
@admin_required
def message_behavior_insights():

    connection = get_db_connection()
    cursor = connection.cursor()

    # =========================
    # UNIQUE SENDERS
    # =========================

    cursor.execute("""
        SELECT COUNT(DISTINCT email)
        FROM contacts
    """)

    unique_senders = cursor.fetchone()[0]

    # =========================
    # REPEAT SENDERS
    # =========================

    cursor.execute("""
        SELECT COUNT(*)
        FROM (
            SELECT email
            FROM contacts
            GROUP BY email
            HAVING COUNT(*) > 1
        )
    """)

    repeat_senders = cursor.fetchone()[0]

    # =========================
    # AVERAGE MESSAGE LENGTH
    # =========================

    cursor.execute("""
        SELECT AVG(LENGTH(message))
        FROM contacts
        WHERE message IS NOT NULL
    """)

    average_message_length = cursor.fetchone()[0] or 0

    average_message_length = round(
        average_message_length,
        2
    )

    # =========================
    # SHORT MESSAGES
    # 1 - 100 characters
    # =========================

    cursor.execute("""
        SELECT COUNT(*)
        FROM contacts
        WHERE LENGTH(message) <= 100
    """)

    short_messages = cursor.fetchone()[0]

    # =========================
    # MEDIUM MESSAGES
    # 101 - 300 characters
    # =========================

    cursor.execute("""
        SELECT COUNT(*)
        FROM contacts
        WHERE LENGTH(message) > 100
        AND LENGTH(message) <= 300
    """)

    medium_messages = cursor.fetchone()[0]

    # =========================
    # LONG MESSAGES
    # 301+ characters
    # =========================

    cursor.execute("""
        SELECT COUNT(*)
        FROM contacts
        WHERE LENGTH(message) > 300
    """)

    long_messages = cursor.fetchone()[0]

    connection.close()

    return {
        "unique_senders": unique_senders,
        "repeat_senders": repeat_senders,
        "average_message_length": average_message_length,
        "short_messages": short_messages,
        "medium_messages": medium_messages,
        "long_messages": long_messages
    }

# =========================
# SMART INSIGHTS SUMMARY
# =========================

@app.route("/admin/dashboard/smart-insights")
@admin_required
def smart_insights_summary():

    connection = get_db_connection()
    cursor = connection.cursor()

    # =========================
    # TOTAL MESSAGES
    # =========================

    cursor.execute("""
        SELECT COUNT(*)
        FROM contacts
    """)

    total_messages = cursor.fetchone()[0]

    # =========================
    # REPLIED MESSAGES
    # =========================

    cursor.execute("""
        SELECT COUNT(*)
        FROM contacts
        WHERE status = 'Replied'
    """)

    replied_messages = cursor.fetchone()[0]

    # =========================
    # RESPONSE RATE
    # =========================

    if total_messages > 0:

        response_rate = round(
            (replied_messages / total_messages) * 100,
            2
        )

    else:

        response_rate = 0

    # =========================
    # BUSIEST DAY
    # =========================

    cursor.execute("""
        SELECT
            DATE(created_at) AS message_date,
            COUNT(*) AS message_count
        FROM contacts
        GROUP BY DATE(created_at)
        ORDER BY message_count DESC
        LIMIT 1
    """)

    busiest_day = cursor.fetchone()

    if busiest_day:

        busiest_date = busiest_day["message_date"]
        busiest_day_count = busiest_day["message_count"]

    else:

        busiest_date = None
        busiest_day_count = 0

    # =========================
    # PEAK HOUR
    # =========================

    cursor.execute("""
        SELECT
            strftime('%H', created_at) AS message_hour,
            COUNT(*) AS message_count
        FROM contacts
        GROUP BY strftime('%H', created_at)
        ORDER BY message_count DESC
        LIMIT 1
    """)

    peak_hour = cursor.fetchone()

    if peak_hour:

        peak_hour_value = peak_hour["message_hour"]
        peak_hour_count = peak_hour["message_count"]

    else:

        peak_hour_value = None
        peak_hour_count = 0

    # =========================
    # AVERAGE MESSAGE LENGTH
    # =========================

    cursor.execute("""
        SELECT AVG(LENGTH(message))
        FROM contacts
        WHERE message IS NOT NULL
    """)

    average_message_length = cursor.fetchone()[0] or 0

    average_message_length = round(
        average_message_length,
        2
    )

    connection.close()

    # =========================
    # SMART SUMMARY
    # =========================

    insights = []

    # Response insight
    if response_rate >= 80:

        insights.append(
            "Excellent response performance. "
            "Most incoming messages have been replied to."
        )

    elif response_rate >= 50:

        insights.append(
            "Your response performance is moderate. "
            "There are still some messages waiting for a reply."
        )

    else:

        insights.append(
            "Your response rate is low. "
            "Consider replying to pending messages more frequently."
        )

    # Busiest day insight
    if busiest_date:

        insights.append(
            f"Your busiest message day was "
            f"{busiest_date}, with "
            f"{busiest_day_count} message(s)."
        )

    # Peak hour insight
    if peak_hour_value:

        hour = int(peak_hour_value)

        if hour == 0:
            formatted_hour = "12 AM"
        elif hour < 12:
            formatted_hour = f"{hour} AM"
        elif hour == 12:
            formatted_hour = "12 PM"
        else:
            formatted_hour = f"{hour - 12} PM"

        insights.append(
            f"Most messages arrive around "
            f"{formatted_hour}."
        )

    # Message length insight
    if average_message_length <= 100:

        insights.append(
            "Visitors generally send short messages."
        )

    elif average_message_length <= 300:

        insights.append(
            "Visitors generally send medium-length messages."
        )

    else:

        insights.append(
            "Visitors tend to send detailed messages."
        )

    return {
        "total_messages": total_messages,
        "response_rate": response_rate,
        "busiest_day": busiest_date,
        "busiest_day_count": busiest_day_count,
        "peak_hour": peak_hour_value,
        "peak_hour_count": peak_hour_count,
        "average_message_length": average_message_length,
        "insights": insights
    }

# =========================
# UPDATE MESSAGE STATUS
# =========================

@app.route("/admin/messages/<int:message_id>/status", methods=["POST"])
@admin_required
def update_status(message_id):

    status = request.form.get(
        "status",
        "New"
    )

    allowed_statuses = [
        "New",
        "Read",
        "Replied"
    ]

    if status not in allowed_statuses:
        return "Invalid status.", 400

    connection = get_db_connection()

    # Get current status
    message = connection.execute(
        """
        SELECT status
        FROM contacts
        WHERE id = ?
        """,
        (message_id,)
    ).fetchone()

    if message is None:
        connection.close()
        return "Message not found.", 404

    old_status = message["status"]

    # Update status
    connection.execute(
        """
        UPDATE contacts
        SET status = ?
        WHERE id = ?
        """,
        (status, message_id)
    )

    connection.commit()
    connection.close()

    # =========================
    # ACTIVITY LOG
    # =========================

    if old_status != status:

        log_activity(
            "Status Changed",
            f"Message status changed from {old_status} to {status}",
            message_id
        )

    flash(
        f"Message marked as {status}.",
        "success"
    )

    return redirect(
        url_for("admin_messages")
    )

# =========================
# DASHBOARD ANALYTICS
# =========================

@app.route("/admin/dashboard/analytics")
@admin_required
def dashboard_analytics():

    connection = get_db_connection()

    range_value = request.args.get("range", "all")

    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    query = """
        SELECT
            DATE(created_at) AS date,
            COUNT(*) AS count
        FROM contacts
    """

    params = []

    # =========================
    # CUSTOM DATE RANGE
    # =========================

    if start_date and end_date:

        query += """
            WHERE DATE(created_at)
            BETWEEN ? AND ?
        """

        params.extend([
            start_date,
            end_date
        ])

        range_value = "custom"

    # =========================
    # PREDEFINED RANGE
    # =========================

    elif range_value in ["7", "30", "90"]:

        query += """
            WHERE DATE(created_at) >= DATE(
                'now',
                ?
            )
        """

        params.append(
            f"-{int(range_value) - 1} days"
        )

    query += """
        GROUP BY DATE(created_at)
        ORDER BY date ASC
    """

    daily_messages = connection.execute(
        query,
        params
    ).fetchall()

    connection.close()

    return {
        "range": range_value,

        "start_date": start_date,

        "end_date": end_date,

        "daily_messages": [
            {
                "date": row["date"],
                "count": row["count"]
            }
            for row in daily_messages
        ]
    }
# =========================
# MESSAGE DAILY AVERAGE
# =========================

@app.route("/admin/dashboard/message-average")
@admin_required
def message_average():

    range_value = request.args.get("range", "all")

    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    connection = get_db_connection()

    date_condition = ""
    params = []

    # =========================
    # CUSTOM DATE RANGE
    # =========================

    if start_date and end_date:

        date_condition = """
            WHERE DATE(created_at)
            BETWEEN ? AND ?
        """

        params.extend([
            start_date,
            end_date
        ])

    # =========================
    # PREDEFINED RANGE
    # =========================

    elif range_value in ["7", "30", "90"]:

        days = int(range_value) - 1

        date_condition = f"""
            WHERE DATE(created_at)
            >= DATE('now', '-{days} days')
        """

    result = connection.execute(
        f"""
        SELECT
            COUNT(*) AS total_messages,
            COUNT(
                DISTINCT DATE(created_at)
            ) AS active_days
        FROM contacts
        {date_condition}
        """,
        params
    ).fetchone()

    connection.close()

    total_messages = result["total_messages"]
    active_days = result["active_days"]

    if active_days > 0:

        average_messages = round(
            total_messages / active_days,
            2
        )

    else:

        average_messages = 0

    return {
        "total_messages": total_messages,
        "active_days": active_days,
        "average_messages": average_messages
    }

# =========================
# MESSAGE GROWTH TREND
# =========================

@app.route("/admin/dashboard/message-growth")
@admin_required
def message_growth():

    range_value = request.args.get("range", "all")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    connection = get_db_connection()

    # =========================
    # CUSTOM DATE RANGE
    # =========================

    if start_date and end_date:

        current_condition = """
            DATE(created_at)
            BETWEEN ? AND ?
        """

        current_params = [
            start_date,
            end_date
        ]

        current_result = connection.execute(
            f"""
            SELECT COUNT(*) AS total
            FROM contacts
            WHERE {current_condition}
            """,
            current_params
        ).fetchone()

        current_start = start_date
        current_end = end_date

        # Calculate previous period
        from datetime import datetime, timedelta

        start_obj = datetime.strptime(
            start_date,
            "%Y-%m-%d"
        )

        end_obj = datetime.strptime(
            end_date,
            "%Y-%m-%d"
        )

        period_days = (
            end_obj - start_obj
        ).days + 1

        previous_end = (
            start_obj - timedelta(days=1)
        )

        previous_start = (
            previous_end -
            timedelta(days=period_days - 1)
        )

        previous_result = connection.execute(
            """
            SELECT COUNT(*) AS total
            FROM contacts
            WHERE DATE(created_at)
            BETWEEN ? AND ?
            """,
            [
                previous_start.strftime("%Y-%m-%d"),
                previous_end.strftime("%Y-%m-%d")
            ]
        ).fetchone()

    # =========================
    # PREDEFINED RANGE
    # =========================

    elif range_value in ["7", "30", "90"]:

        days = int(range_value)

        current_result = connection.execute(
            f"""
            SELECT COUNT(*) AS total
            FROM contacts
            WHERE DATE(created_at)
            >= DATE('now', '-{days - 1} days')
            """
        ).fetchone()

        previous_result = connection.execute(
            f"""
            SELECT COUNT(*) AS total
            FROM contacts
            WHERE DATE(created_at)
            BETWEEN
                DATE('now', '-{(days * 2) - 1} days')
                AND
                DATE('now', '-{days} days')
            """
        ).fetchone()

    # =========================
    # ALL TIME
    # =========================

    else:

        current_result = connection.execute(
            """
            SELECT COUNT(*) AS total
            FROM contacts
            """
        ).fetchone()

        previous_result = connection.execute(
            """
            SELECT COUNT(*) AS total
            FROM contacts
            WHERE 1 = 0
            """
        ).fetchone()

    connection.close()

    current_total = (
        current_result["total"] or 0
    )

    previous_total = (
        previous_result["total"] or 0
    )

    # =========================
    # GROWTH CALCULATION
    # =========================

    if previous_total > 0:

        growth = (
            (current_total - previous_total)
            / previous_total
        ) * 100

    elif current_total > 0:

        growth = 100

    else:

        growth = 0

    return {
        "current_messages": current_total,
        "previous_messages": previous_total,
        "growth": round(growth, 2)
    }

# =========================
# MESSAGE GROWTH CHART DATA
# =========================

@app.route("/admin/dashboard/message-growth-chart")
@admin_required
def message_growth_chart():

    range_value = request.args.get("range", "all")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    connection = get_db_connection()

    date_condition = ""
    params = []

    # =========================
    # CUSTOM DATE RANGE
    # =========================

    if start_date and end_date:

        date_condition = """
            WHERE DATE(created_at)
            BETWEEN ? AND ?
        """

        params = [
            start_date,
            end_date
        ]

    # =========================
    # PREDEFINED RANGE
    # =========================

    elif range_value in ["7", "30", "90"]:

        days = int(range_value) - 1

        date_condition = f"""
            WHERE DATE(created_at)
            >= DATE('now', '-{days} days')
        """

    # =========================
    # DAILY MESSAGE DATA
    # =========================

    rows = connection.execute(
        f"""
        SELECT
            DATE(created_at) AS message_date,
            COUNT(*) AS message_count
        FROM contacts
        {date_condition}
        GROUP BY DATE(created_at)
        ORDER BY DATE(created_at)
        """,
        params
    ).fetchall()

    connection.close()

    labels = []
    data = []

    for row in rows:

        labels.append(
            row["message_date"]
        )

        data.append(
            row["message_count"]
        )

    return {
        "labels": labels,
        "data": data
    }

# =========================
# TOP CONTACT DAYS
# =========================

@app.route("/admin/dashboard/top-contact-days")
@admin_required
def top_contact_days():

    range_value = request.args.get("range", "all")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    connection = get_db_connection()

    date_condition = ""
    params = []

    # =========================
    # CUSTOM DATE RANGE
    # =========================

    if start_date and end_date:

        date_condition = """
            WHERE DATE(created_at)
            BETWEEN ? AND ?
        """

        params = [
            start_date,
            end_date
        ]

    # =========================
    # PREDEFINED RANGE
    # =========================

    elif range_value in ["7", "30", "90"]:

        days = int(range_value) - 1

        date_condition = f"""
            WHERE DATE(created_at)
            >= DATE('now', '-{days} days')
        """

    # =========================
    # WEEKDAY ANALYTICS
    # =========================

    rows = connection.execute(
        f"""
        SELECT
            CASE strftime('%w', created_at)

                WHEN '0' THEN 'Sunday'
                WHEN '1' THEN 'Monday'
                WHEN '2' THEN 'Tuesday'
                WHEN '3' THEN 'Wednesday'
                WHEN '4' THEN 'Thursday'
                WHEN '5' THEN 'Friday'
                WHEN '6' THEN 'Saturday'

            END AS day_name,

            COUNT(*) AS message_count

        FROM contacts

        {date_condition}

        GROUP BY strftime(
            '%w',
            created_at
        )

        ORDER BY
            message_count DESC
        """,
        params
    ).fetchall()

    connection.close()

    labels = []
    data = []

    for row in rows:

        labels.append(
            row["day_name"]
        )

        data.append(
            row["message_count"]
        )

    return {
        "labels": labels,
        "data": data
    }

# =========================
# MESSAGE STATUS DISTRIBUTION
# =========================

@app.route("/admin/dashboard/status-distribution")
@admin_required
def status_distribution():

    range_value = request.args.get(
        "range",
        "all"
    )

    start_date = request.args.get(
        "start_date"
    )

    end_date = request.args.get(
        "end_date"
    )

    connection = get_db_connection()

    date_condition = ""

    params = []

    # =========================
    # CUSTOM DATE RANGE
    # =========================

    if start_date and end_date:

        date_condition = """
            AND DATE(created_at)
            BETWEEN ? AND ?
        """

        params = [
            start_date,
            end_date
        ]

    # =========================
    # PREDEFINED RANGE
    # =========================

    elif range_value in [
        "7",
        "30",
        "90"
    ]:

        days = int(range_value) - 1

        date_condition = f"""
            AND DATE(created_at)
            >= DATE(
                'now',
                '-{days} days'
            )
        """

    # =========================
    # STATUS DATA
    # =========================

    rows = connection.execute(
        f"""
        SELECT
            status,
            COUNT(*) AS message_count

        FROM contacts

        WHERE 1 = 1

        {date_condition}

        GROUP BY status

        ORDER BY
            message_count DESC
        """,
        params
    ).fetchall()

    connection.close()

    labels = []
    data = []

    for row in rows:

        labels.append(
            row["status"]
        )

        data.append(
            row["message_count"]
        )

    return {
        "labels": labels,
        "data": data
    }

# =========================
# RESPONSE TIME ANALYTICS
# =========================

@app.route("/admin/dashboard/response-time")
@admin_required
def response_time_analytics():

    connection = get_db_connection()
    cursor = connection.cursor()

    range_value = request.args.get(
        "range",
        "all"
    )

    start_date = request.args.get(
        "start_date"
    )

    end_date = request.args.get(
        "end_date"
    )

    date_condition = ""
    params = []

    # =========================
    # CUSTOM DATE RANGE
    # =========================

    if start_date and end_date:

        date_condition = """
            AND DATE(c.created_at)
            BETWEEN ? AND ?
        """

        params = [
            start_date,
            end_date
        ]

    # =========================
    # PREDEFINED RANGE
    # =========================

    elif range_value in [
        "7",
        "30",
        "90"
    ]:

        days = int(range_value) - 1

        date_condition = f"""
            AND DATE(c.created_at)
            >= DATE(
                'now',
                '-{days} days'
            )
        """

    # =========================
    # RESPONSE TIME
    # =========================

    rows = connection.execute(
        f"""
        SELECT
            c.created_at,
            c.replied_at

        FROM contacts c

        WHERE c.replied_at IS NOT NULL

        {date_condition}
        """,
        params
    ).fetchall()

    # =========================
    # RESPONSE TIME DISTRIBUTION
    # =========================

    distribution_condition = ""

    distribution_params = []

    if start_date and end_date:

        distribution_condition = """
            AND DATE(created_at)
            BETWEEN ? AND ?
        """

        distribution_params = [
            start_date,
            end_date
        ]

    elif range_value in ["7", "30", "90"]:

        days = int(range_value) - 1

        distribution_condition = f"""
            AND DATE(created_at)
            >= DATE('now', '-{days} days')
        """

    distribution_rows = connection.execute(
        f"""
        SELECT
            CASE
                WHEN (
                    (julianday(replied_at)
                    - julianday(created_at)) * 86400
                ) < 900
                    THEN 'Under 15 Minutes'

                WHEN (
                    (julianday(replied_at)
                    - julianday(created_at)) * 86400
                ) < 3600
                    THEN '15-60 Minutes'

                WHEN (
                    (julianday(replied_at)
                    - julianday(created_at)) * 86400
                ) < 14400
                    THEN '1-4 Hours'

                ELSE 'Over 4 Hours'
            END AS response_range,

            COUNT(*) AS response_count

        FROM contacts

        WHERE replied_at IS NOT NULL

        {distribution_condition}

        GROUP BY response_range

        ORDER BY
            CASE response_range
                WHEN 'Under 15 Minutes' THEN 1
                WHEN '15-60 Minutes' THEN 2
                WHEN '1-4 Hours' THEN 3
                WHEN 'Over 4 Hours' THEN 4
            END
        """,
        distribution_params
    ).fetchall()

    connection.close()

    response_times = []

    from datetime import datetime

    for row in rows:

        try:

            created =datetime.fromisoformat(
                    row["created_at"]
                )

            replied =datetime.fromisoformat(
                    row["replied_at"]
                )

            seconds = (
                replied - created
            ).total_seconds()

            if seconds >= 0:

                response_times.append(
                    seconds
                )

        except Exception:

            continue

    # =========================
    # CALCULATE RESULTS
    # =========================

    if response_times:

        average_seconds = (
            sum(response_times)
            / len(response_times)
        )

        fastest_seconds = min(
            response_times
        )

        slowest_seconds = max(
            response_times
        )

    else:

        average_seconds = 0
        fastest_seconds = 0
        slowest_seconds = 0

    # =========================
    # API RESPONSE
    # =========================

    return {
        "average_seconds":
            round(
                average_seconds,
                2
            ),

        "fastest_seconds":
            round(
                fastest_seconds,
                2
            ),

        "slowest_seconds":
            round(
                slowest_seconds,
                2
            ),

        "responses":
            len(response_times),

        "distribution": [
            {
                "range":
                    row["response_range"],

                "count":
                    row["response_count"]
            }

            for row in distribution_rows
        ]
    }
# =========================
# MESSAGE RESPONSE RATE
# =========================

@app.route("/admin/dashboard/response-rate")
@admin_required
def message_response_rate():

    range_value = request.args.get("range", "all")

    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    connection = get_db_connection()

    date_condition = ""
    params = []

    # =========================
    # CUSTOM DATE RANGE
    # =========================

    if start_date and end_date:

        date_condition = """
            WHERE DATE(created_at)
            BETWEEN ? AND ?
        """

        params.extend([
            start_date,
            end_date
        ])

    # =========================
    # PREDEFINED RANGE
    # =========================

    elif range_value in ["7", "30", "90"]:

        days = int(range_value) - 1

        date_condition = f"""
            WHERE DATE(created_at)
            >= DATE('now', '-{days} days')
        """

    result = connection.execute(
        f"""
        SELECT
            COUNT(*) AS total_messages,

            SUM(
                CASE
                    WHEN status = 'Replied'
                    THEN 1
                    ELSE 0
                END
            ) AS replied_messages

        FROM contacts

        {date_condition}
        """,
        params
    ).fetchone()

    connection.close()

    total_messages =result["total_messages"]

    replied_messages =result["replied_messages"] or 0

    if total_messages > 0:

        response_rate = round(
            (replied_messages / total_messages) * 100,
            2
        )

    else:

        response_rate = 0

    return {
        "total_messages": total_messages,
        "replied_messages": replied_messages,
        "response_rate": response_rate
    }
# =========================
# MESSAGE STATUS ANALYTICS
# =========================

@app.route("/admin/dashboard/message-status")
@admin_required
def message_status_analytics():

    connection = get_db_connection()

    status_data = connection.execute(
        """
        SELECT
            status,
            COUNT(*) AS count
        FROM contacts
        GROUP BY status
        """
    ).fetchall()

    connection.close()

    return {
        "status_data": [
            {
                "status": row["status"],
                "count": row["count"]
            }
            for row in status_data
        ]
    }

# =========================
# DELETE MESSAGE
# =========================

@app.route("/admin/messages/<int:message_id>/delete", methods=["POST"])
@admin_required
def delete_message(message_id):

    connection = get_db_connection()

    # Get message details before deleting
    message = connection.execute(
        """
        SELECT name
        FROM contacts
        WHERE id = ?
        """,
        (message_id,)
    ).fetchone()

    if message is None:
        connection.close()
        return "Message not found.", 404

    message_name = message["name"]

    # Delete message
    connection.execute(
        """
        DELETE FROM contacts
        WHERE id = ?
        """,
        (message_id,)
    )

    connection.commit()
    connection.close()

    # =========================
    # ACTIVITY LOG
    # =========================

    log_activity(
        "Message Deleted",
        f"Admin deleted message from {message_name}",
        message_id
    )

    flash(
        "Message deleted successfully.",
        "success"
    )

    return redirect(
        url_for("admin_messages")
    )

# =========================
# REPLY MESSAGE
# =========================

@app.route("/admin/messages/<int:message_id>/reply", methods=["POST"])
@admin_required
def reply_to_message(message_id):

    reply = request.form.get("reply", "").strip()

    if not reply:
        flash("Reply cannot be empty.", "error")
        return redirect(
            url_for("view_message", message_id=message_id)
        )

    connection = get_db_connection()

    message = connection.execute(
        "SELECT * FROM contacts WHERE id = ?",
        (message_id,)
    ).fetchone()

    if message is None:
        connection.close()
        return "Message not found.", 404

    connection.execute(
        """
        UPDATE contacts
        SET reply = ?,
            replied_at = CURRENT_TIMESTAMP,
            replied_by = ?,
            status = 'Replied'
        WHERE id = ?
        """,
        (
            reply,
            session.get("admin_username", "Admin"),
            message_id
        )
    )

    connection.commit()
    connection.close()

    # =========================
    # ACTIVITY LOG
    # =========================

    log_activity(
        "Reply Sent",
        f"Admin replied to message from {message['name']}",
        message_id
    )

    try:
        send_reply_email(
            message["email"],
            reply,
            message["name"]
        )

        flash(
            "Reply sent successfully.",
            "success"
        )

    except Exception as e:
        print("EMAIL ERROR:", e)

        flash(
            "Reply saved, but email could not be sent.",
            "error"
        )

    return redirect(
        url_for("view_message", message_id=message_id)
    )

# =========================
# ADMIN ACTIVITY LOG
# =========================

@app.route("/admin/activity-log")
@admin_required
def admin_activity_log():

    search = request.args.get(
        "search",
        ""
    ).strip()

    action_filter = request.args.get(
        "action",
        ""
    ).strip()
    from_date = request.args.get(
        "from_date",
        ""
    ).strip()

    to_date = request.args.get(
        "to_date",
        ""
    ).strip()

    # =========================
    # PAGINATION
    # =========================

    page = request.args.get(
        "page",
        1,
        type=int
    )

    if page < 1:
        page = 1

    per_page = 10

    offset = (page - 1) * per_page

    connection = get_db_connection()

    # =========================
    # BASE QUERY
    # =========================

    query = """
        SELECT *
        FROM activity_logs
        WHERE 1 = 1
    """

    parameters = []

    # =========================
    # SEARCH
    # =========================

    if search:

        query += """
            AND (
                admin_username LIKE ?
                OR action LIKE ?
                OR description LIKE ?
            )
        """

        search_value = f"%{search}%"

        parameters.extend([
            search_value,
            search_value,
            search_value
        ])

    # =========================
    # DATE RANGE FILTER
    # =========================

    if from_date:
        query += """
            AND DATE(created_at) >= DATE(?)
        """

        parameters.append(from_date)

    if to_date:
        query += """
            AND DATE(created_at) <= DATE(?)
        """

        parameters.append(to_date)

    # =========================
    # ACTION FILTER
    # =========================

    if action_filter:

        query += """
            AND action = ?
        """

        parameters.append(action_filter)

    # =========================
    # TOTAL ACTIVITIES
    # =========================

    count_query = query.replace(
        "SELECT *",
        "SELECT COUNT(*)"
    )

    total_activities = connection.execute(
        count_query,
        parameters
    ).fetchone()[0]

    # =========================
    # TOTAL PAGES
    # =========================

    total_pages = max(
        1,
        (total_activities + per_page - 1)
        // per_page
    )

    if page > total_pages:

        page = total_pages

        offset = (page - 1) * per_page

    # =========================
    # GET ACTIVITIES
    # =========================

    query += """
        ORDER BY created_at DESC
        LIMIT ?
        OFFSET ?
    """

    activity_parameters = parameters + [
        per_page,
        offset
    ]

    activities = connection.execute(
        query,
        activity_parameters
    ).fetchall()

    # =========================
    # ACTIVITY STATISTICS
    # =========================

    login_count = connection.execute(
        """
        SELECT COUNT(*)
        FROM activity_logs
        WHERE action = 'Login'
        """
    ).fetchone()[0]

    message_activity_count = connection.execute(
    """
    SELECT COUNT(*)
    FROM activity_logs
    WHERE action IN (
        'Read Message',
        'Status Changed',
        'Message Deleted',
        'Reply Sent'
    )
    """
).fetchone()[0]

    reply_count = connection.execute(
        """
        SELECT COUNT(*)
        FROM activity_logs
        WHERE action = 'Reply Sent'
        """
    ).fetchone()[0]

    connection.close()

    # =========================
    # ACTION LIST
    # =========================

    actions = [
    "Login",
    "Logout",
    "Password Changed",
    "Read Message",
    "Status Changed",
    "Message Deleted",
    "Reply Sent",
    "Notification Read",
    "Notifications Marked Read"
]

    return render_template(
        "admin_activity_log.html",

        activities=activities,

        total_activities=total_activities,
        login_count=login_count,
        message_activity_count=message_activity_count,
        reply_count=reply_count,

        actions=actions,

        search=search,
        action_filter=action_filter,

        page=page,
        per_page=per_page,
        total_pages=total_pages,
        from_date=from_date,
        to_date=to_date,
    )

# =========================
# ACTIVITY LOG DETAILS
# =========================

@app.route("/admin/activity-log/<int:log_id>")
@admin_required
def activity_log_detail(log_id):

    connection = get_db_connection()

    activity = connection.execute(
        """
        SELECT *
        FROM activity_logs
        WHERE id = ?
        """,
        (log_id,)
    ).fetchone()

    connection.close()

    if activity is None:
        flash("Activity log not found.", "error")
        return redirect(url_for("admin_activity_log"))

    return render_template(
        "admin_activity_detail.html",
        activity=activity
    )

# =========================
# DELETE INDIVIDUAL ACTIVITY LOG
# =========================

@app.route("/admin/activity-log/<int:log_id>/delete", methods=["POST"])
@admin_required
def delete_activity_log(log_id):

    connection = get_db_connection()

    # Check if activity log exists
    activity = connection.execute(
        """
        SELECT *
        FROM activity_logs
        WHERE id = ?
        """,
        (log_id,)
    ).fetchone()

    if activity is None:
        connection.close()

        flash(
            "Activity log not found.",
            "error"
        )

        return redirect(
            url_for("admin_activity_log")
        )

    # Delete activity log
    connection.execute(
        """
        DELETE FROM activity_logs
        WHERE id = ?
        """,
        (log_id,)
    )

    connection.commit()
    connection.close()

    flash(
        "Activity log deleted successfully.",
        "success"
    )

    return redirect(
        url_for("admin_activity_log")
    )


# =========================
# CLEAR ALL ACTIVITY LOGS
# =========================

@app.route("/admin/activity-log/clear", methods=["POST"])
@admin_required
def clear_activity_logs():

    connection = get_db_connection()

    # Count logs before deleting
    total_logs = connection.execute(
        """
        SELECT COUNT(*)
        FROM activity_logs
        """
    ).fetchone()[0]

    if total_logs == 0:
        connection.close()

        flash(
            "There are no activity logs to clear.",
            "error"
        )

        return redirect(
            url_for("admin_activity_log")
        )

    # Delete all activity logs
    connection.execute(
        """
        DELETE FROM activity_logs
        """
    )

    connection.commit()
    connection.close()

    flash(
        "All activity logs cleared successfully.",
        "success"
    )

    return redirect(
        url_for("admin_activity_log")
    )

# =========================
# EXPORT ACTIVITY LOGS
# =========================

@app.route("/admin/activity-log/export")
@admin_required
def export_activity_logs():

    search = request.args.get(
        "search",
        ""
    ).strip()

    action_filter = request.args.get(
        "action",
        ""
    ).strip()

    connection = get_db_connection()

    query = """
        SELECT *
        FROM activity_logs
        WHERE 1 = 1
    """

    parameters = []

    # =========================
    # SEARCH FILTER
    # =========================

    if search:

        query += """
            AND (
                admin_username LIKE ?
                OR action LIKE ?
                OR description LIKE ?
            )
        """

        search_value = f"%{search}%"

        parameters.extend([
            search_value,
            search_value,
            search_value
        ])

    # =========================
    # ACTION FILTER
    # =========================

    if action_filter:

        query += """
            AND action = ?
        """

        parameters.append(
            action_filter
        )

    from_date = request.args.get(
        "from_date",
        ""
    ).strip()

    to_date = request.args.get(
        "to_date",
        ""
    ).strip()

    # =========================
    # DATE RANGE FILTER
    # =========================

    if from_date:

        query += """
            AND DATE(created_at) >= DATE(?)
        """

        parameters.append(from_date)

    if to_date:

        query += """
            AND DATE(created_at) <= DATE(?)
        """

        parameters.append(to_date)

    # =========================
    # ORDER
    # =========================

    query += """
        ORDER BY created_at DESC
    """

    activities = connection.execute(
        query,
        parameters
    ).fetchall()

    connection.close()

    # =========================
    # CREATE CSV
    # =========================

    output = io.StringIO()

    writer = csv.writer(output)

    writer.writerow([
        "ID",
        "Admin",
        "Action",
        "Description",
        "Message ID",
        "Date"
    ])

    for activity in activities:

        writer.writerow([
            activity["id"],
            activity["admin_username"],
            activity["action"],
            activity["description"] or "",
            activity["message_id"] or "",
            activity["created_at"]
        ])

    # =========================
    # RETURN CSV FILE
    # =========================

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition":
                "attachment; filename=activity_logs.csv"
        }
    )

# =========================
# EXPORT ANALYTICS
# =========================

@app.route("/admin/dashboard/analytics/export")
@admin_required
def export_analytics():

    range_value = request.args.get("range", "all")

    if range_value not in ["all", "7", "30", "90"]:
        range_value = "all"

    connection = get_db_connection()

        # =========================
    # DATE RANGE FILTER
    # =========================

    date_condition = ""

    if range_value in ["7", "30", "90"]:

        days = int(range_value) - 1

        date_condition = f"""
            WHERE DATE(created_at) >= DATE('now', '-{days} days')
        """
    # =========================
    # BASIC MESSAGE STATISTICS
    # =========================

    total_messages = connection.execute(
    f"""
    SELECT COUNT(*)
    FROM contacts
    {date_condition}
    """
).fetchone()[0]

    new_messages = connection.execute(
    f"""
    SELECT COUNT(*)
    FROM contacts
    {date_condition}
    {"AND" if date_condition else "WHERE"} status = 'New'
    """
).fetchone()[0]

    read_messages = connection.execute(
    f"""
    SELECT COUNT(*)
    FROM contacts
    {date_condition}
    {"AND" if date_condition else "WHERE"} status = 'Read'
    """
).fetchone()[0]

    replied_messages = connection.execute(
    f"""
    SELECT COUNT(*)
    FROM contacts
    {date_condition}
    {"AND" if date_condition else "WHERE"} status = 'Replied'
    """
).fetchone()[0]

    # =========================
    # DAILY AVERAGE
    # =========================

    average_result = connection.execute(
    f"""
    SELECT
        COUNT(*) AS total_messages,
        COUNT(DISTINCT DATE(created_at)) AS active_days
    FROM contacts
    {date_condition}
    """
).fetchone()

    active_days = average_result["active_days"]

    if active_days > 0:
        average_messages = round(
            total_messages / active_days,
            2
        )
    else:
        average_messages = 0

    # =========================
    # RESPONSE RATE
    # =========================

    if total_messages > 0:
        response_rate = round(
            (replied_messages / total_messages) * 100,
            2
        )
    else:
        response_rate = 0

    # =========================
    # STATUS ANALYTICS
    # =========================

    status_data = connection.execute(
    f"""
    SELECT
        status,
        COUNT(*) AS count
    FROM contacts
    {date_condition}
    GROUP BY status
    ORDER BY status
    """
).fetchall()

    # =========================
    # DAILY MESSAGE ANALYTICS
    # =========================

    daily_messages = connection.execute(
    f"""
    SELECT
        DATE(created_at) AS date,
        COUNT(*) AS count
    FROM contacts
    {date_condition}
    GROUP BY DATE(created_at)
    ORDER BY date ASC
    """
).fetchall()

    connection.close()

    # =========================
    # CREATE CSV
    # =========================

    output = io.StringIO()

    writer = csv.writer(output)

    # =========================
    # REPORT HEADER
    # =========================

    writer.writerow([
    "Portfolio Analytics Report"
])

    writer.writerow([
    "Analytics Range",
    "All Time" if range_value == "all" else f"Last {range_value} Days"
])

    writer.writerow([])

    # =========================
    # SUMMARY
    # =========================

    writer.writerow([
        "Metric",
        "Value"
    ])

    writer.writerow([
        "Total Messages",
        total_messages
    ])

    writer.writerow([
        "New Messages",
        new_messages
    ])

    writer.writerow([
        "Read Messages",
        read_messages
    ])

    writer.writerow([
        "Replied Messages",
        replied_messages
    ])

    writer.writerow([
        "Active Days",
        active_days
    ])

    writer.writerow([
        "Average Messages Per Active Day",
        average_messages
    ])

    writer.writerow([
        "Response Rate (%)",
        response_rate
])
    writer.writerow([])
    # =========================
    # STATUS BREAKDOWN
    # =========================

    writer.writerow([
        "Status",
        "Count"
    ])

    for row in status_data:

        writer.writerow([
            row["status"],
            row["count"]
        ])

    writer.writerow([])

    # =========================
    # DAILY MESSAGE BREAKDOWN
    # =========================

    writer.writerow([
        "Date",
        "Messages"
    ])

    for row in daily_messages:

        writer.writerow([
            row["date"],
            row["count"]
        ])

    # =========================
    # ACTIVITY LOG
    # =========================

    log_activity(
        "Analytics Exported",
        "Admin exported the analytics report"
    )

    # =========================
    # RETURN CSV
    # =========================

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition":
                "attachment; filename=analytics_report.csv"
        }
    )

# =========================
# MONTHLY ANALYTICS
# =========================

@app.route("/admin/dashboard/monthly-analytics")
@admin_required
def monthly_analytics():

    connection = get_db_connection()

    monthly_data = connection.execute(
        """
        SELECT
            strftime('%Y-%m', created_at) AS month,
            COUNT(*) AS count
        FROM contacts
        GROUP BY strftime('%Y-%m', created_at)
        ORDER BY month ASC
        """
    ).fetchall()

    connection.close()

    return {
    "labels": [
        datetime.strptime(
            row["month"],
            "%Y-%m"
        ).strftime("%b %Y")
        for row in monthly_data
    ],

    "data": [
        row["count"]
        for row in monthly_data
    ]
}
# =========================
# MOST ACTIVE DAY
# =========================

@app.route("/admin/dashboard/most-active-day")
@admin_required
def most_active_day():

    range_value = request.args.get("range", "all")

    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    connection = get_db_connection()

    date_condition = ""
    params = []


    # =========================
    # CUSTOM DATE RANGE
    # =========================

    if start_date and end_date:

        date_condition = """
            WHERE DATE(created_at)
            BETWEEN ? AND ?
        """

        params.extend([
            start_date,
            end_date
        ])

    # =========================
    # PREDEFINED RANGE
    # =========================

    elif range_value in ["7", "30", "90"]:

        days = int(range_value) - 1

        date_condition = f"""
            WHERE DATE(created_at)
            >= DATE('now', '-{days} days')
        """

    result = connection.execute(
        f"""
        SELECT
            DATE(created_at) AS date,
            COUNT(*) AS count

        FROM contacts

        {date_condition}

        GROUP BY DATE(created_at)

        ORDER BY count DESC

        LIMIT 1
        """,
        params
    ).fetchone()

    connection.close()

    if result:

        return {
            "date": datetime.strptime(
                result["date"],
                "%Y-%m-%d"
            ).strftime("%d %b %Y"),

            "count": result["count"]
        }

    return {
        "date": None,
        "count": 0
    }
# =========================
# PEAK MESSAGE HOUR
# =========================

@app.route("/admin/dashboard/peak-hour")
@admin_required
def peak_message_hour():

    range_value = request.args.get("range", "all")

    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    connection = get_db_connection()

    date_condition = ""
    params = []

    # =========================
    # CUSTOM DATE RANGE
    # =========================

    if start_date and end_date:

        date_condition = """
            WHERE DATE(created_at)
            BETWEEN ? AND ?
        """

        params.extend([
            start_date,
            end_date
        ])

    # =========================
    # PREDEFINED RANGE
    # =========================

    elif range_value in ["7", "30", "90"]:

        days = int(range_value) - 1

        date_condition = f"""
            WHERE DATE(created_at)
            >= DATE('now', '-{days} days')
        """

    result = connection.execute(
        f"""
        SELECT
            strftime('%H', created_at) AS hour,
            COUNT(*) AS count

        FROM contacts

        {date_condition}

        GROUP BY strftime('%H', created_at)

        ORDER BY count DESC

        LIMIT 1
        """,
        params
    ).fetchone()

    connection.close()

    if result:

        hour = int(result["hour"])

        return {
            "hour": datetime.strptime(
                f"{hour:02d}",
                "%H"
            ).strftime("%I %p"),

            "count": result["count"]
        }

    return {
        "hour": None,
        "count": 0
    }

# =========================
# START FLASK
# =========================

if __name__ == "__main__":

    init_db()

    debug_mode = os.getenv(
        "FLASK_DEBUG",
        "false"
    ).lower() == "true"

    app.run(
        debug=debug_mode
    )
