import os
import smtplib
from email.mime.text import MIMEText

# RECIPIENT = SMTP_RECIPIENT
SUBJECT = "Thermal Comfort Analysis"

def send_email(body: str) -> None:
	sender = os.environ["SMTP_USER"]
	password = os.environ["SMTP_PASSWORD"]
	
	msg = MIMEText(body)
	msg["Subject"] = SUBJECT
	msg["from"] = sender
	msg["To"] = SMTP_RECIPIENT
	
	with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
		server.login(sender, password)
		server.sendmail(sender, SMTP_RECIPIENT, msg.as_string())
		
	print(f"Email sent to {SMTP_RECIPIENT}")
