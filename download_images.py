import urllib.request
import os

artifact_dir = r"C:\Users\sai\.gemini\antigravity\brain\f5388129-e67d-4b35-881e-aaa2dffd3937\artifacts"
os.makedirs(artifact_dir, exist_ok=True)

desktop_url = "https://lh3.googleusercontent.com/aida/ADBb0uhwNyKdIIZbll-GIg5uDRB4eztviJ_g2joAu9nG5yrkFXfwlYAlErennw5TK6oJf9IxndO51denOMyh3qxiqgR5UhoFHCsowGFbDiE2bu4--_Apl4XMa0gSYU3cZVTbaJ_cB_inPJpGrP9MPWJM9w-7QcTYALMVLIQ9IOOlO8f0USONdK_ctIZQUwuj53rtE0bLDNR3dPcYeSDG68IIsk9BX3NQ9ZzFeNOUT872IfQFriC7ONxLf-U9hqY"
mobile_url = "https://lh3.googleusercontent.com/aida/ADBb0uhm3vmNPAfe3400CMWFL7YR2cv_fgMrdqchJJsingYxdodvgvbRdapeE4XuYwDg-I3nD_eT__N7iIaxXJQq6kI_r2Eo6K3p2mXXkWmws7FS7PYcdD1DRTU0fWqlmzAj28OsOn7byQDBnrA26DcozcNXECFIm_ywHOijBA7dL08vDS6-Ankrt-JpKxhXgck9xvhuqnTPjDmKcWQCyOlQHnV91ShYO6iPq1KdO3ioEtSTUSsQTcrwOVJ1jI8"

try:
    urllib.request.urlretrieve(desktop_url, os.path.join(artifact_dir, "desktop_chat.png"))
    urllib.request.urlretrieve(mobile_url, os.path.join(artifact_dir, "mobile_chat.png"))
    print("Downloaded successfully")
except Exception as e:
    print(f"Failed: {e}")
