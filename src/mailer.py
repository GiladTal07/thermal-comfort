import os
import smtplib
import markdown
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

SUBJECT = "Thermal Comfort Analysis"

def send_email(body: str, photo: Path | None = None, heatmap: Path | None = None) -> None:
    sender = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASSWORD"]
    recipient = os.environ["SMTP_RECIPIENT"]

    template_path = os.path.join(os.path.dirname(__file__), "template.html")
    with open(template_path) as f:
        template = f.read()

    images_html = ""
    if photo or heatmap:
        images_html += '<div class="appendix">'
        if photo:
            images_html += (
                '<h2>Appendix B &mdash; Room Photo</h2>'
                '<div class="img-block">'
                '<img src="cid:photo">'
                '<p class="img-label">Camera photo &middot; 1920 &times; 1080</p>'
                '</div>'
            )
        if heatmap:
            images_html += (
                '<h2>Appendix C &mdash; Thermal Heatmap</h2>'
                '<div class="img-block">'
                '<img src="cid:heatmap">'
                '<p class="img-label">'
                'MLX90640 infrared array &middot; bicubic-upscaled &middot; '
                'inferno colormap (brighter&nbsp;=&nbsp;warmer)'
                '</p>'
                '</div>'
            )
        images_html += '</div>'

    html_content = markdown.markdown(body, extensions=["tables", "extra"])
    html_body = template.replace("{content}", html_content).replace("{images}", images_html)

    related = MIMEMultipart("related")

    alternative = MIMEMultipart("alternative")
    alternative.attach(MIMEText(body, "plain"))
    alternative.attach(MIMEText(html_body, "html"))
    related.attach(alternative)

    if photo:
        img = MIMEImage(Path(photo).read_bytes(), _subtype="jpeg")
        img.add_header("Content-ID", "<photo>")
        img.add_header("Content-Disposition", "inline")
        related.attach(img)

    if heatmap:
        img = MIMEImage(Path(heatmap).read_bytes(), _subtype="png")
        img.add_header("Content-ID", "<heatmap>")
        img.add_header("Content-Disposition", "inline")
        related.attach(img)

    outer = MIMEMultipart("mixed")
    outer["Subject"] = SUBJECT
    outer["From"] = sender
    outer["To"] = recipient
    outer.attach(related)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.sendmail(sender, recipient, outer.as_string())

    print(f"Email sent to {recipient}")
