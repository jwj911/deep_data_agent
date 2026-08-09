import win32com.client
import pythoncom
def draft(to_list:list = [], cc_list:list = [], subject:str = "", body:str = "", attachments:list = []):
    pythoncom.CoInitialize()
    outlook = win32com.client.Dispatch("Outlook.Application")
    mail = outlook.CreateItem(0)  # 0表示邮件项
    mail.To = ";".join(to_list)
    if len(cc_list) > 0:
        mail.CC = ";".join(cc_list)
    for path in attachments:
        mail.Attachments.Add(path)
    mail.Subject = subject
    mail.Body = body
    mail.Save()  # 保存到草稿箱