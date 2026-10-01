def build_email_template(title, content_html):
    
    """Builds a complete HTML email template with the given title and content."""

    return f"""
    <html>
    <body style="font-family: Arial, sans-serif; background-color:#f4f6f8; padding:20px;">
        
        <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
                <td align="center">
                    
                    <table width="600px" style="background:#ffffff; border-radius:8px; padding:20px;">
                        
                        <!-- Header -->
                        <tr>
                            <td style="background:#0d6efd; color:white; padding:15px; border-radius:6px;">
                                <h2 style="margin:0;">{title}</h2>
                            </td>
                        </tr>

                        <!-- Body -->
                        <tr>
                            <td style="padding:20px; color:#333;">
                                {content_html}
                            </td>
                        </tr>

                        <!-- Footer -->
                        <tr>
                            <td style="padding:15px; font-size:12px; color:#777; border-top:1px solid #eee;">
                                <p style="font-size:12px;color:gray;">
                                This is an automated notification. Please do not reply to this email.
                                </p>
                            </td>
                        </tr>

                    </table>

                </td>
            </tr>
        </table>

    </body>
    </html>
    """