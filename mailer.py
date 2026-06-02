import os
import smtplib
from email.mime.text import MIMEText

# RECIPIENT = SMTP_RECIPIENT
SUBJECT = "Thermal Comfort Analysis"

def send_email(body: str) -> None:
	sender = os.environ["SMTP_USER"]
	password = os.environ["SMTP_PASSWORD"]
	recipient = os.environ["SMTP_RECIPIENT"]
	
	msg = MIMEText(body)
	msg["Subject"] = SUBJECT
	msg["from"] = sender
	msg["To"] = recipient
	
	with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
		server.login(sender, password)
		server.sendmail(sender, recipient, msg.as_string())
		
	print(f"Email sent to {recipient}")
