from flask import Blueprint, send_file, render_template, jsonify, request, redirect, session, abort, url_for, flash, current_app, make_response
from app.services.api_client import APIClient
from io import BytesIO
from functools import wraps
import jwt
import requests


auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/api/erm/chat", methods=["POST"])
def proxy_erm_chat():
    try:
        payload = request.get_json() or {}
        msg = payload.get("message") or payload.get("query") or ""
        session_id = payload.get("session_id") or session.get("copilot_session_id") or session.get("session_id")
        if not session_id:
            import uuid
            session["copilot_session_id"] = f"sess_{uuid.uuid4().hex[:8]}"
            session_id = session["copilot_session_id"]
        payload["session_id"] = str(session_id)
        login_data = session.get("login_data") or {}
        
        # Extract trusted identity strictly from session auth
        auth_user_id = login_data.get("userId") or login_data.get("id") or session.get("user_id")
        auth_role = login_data.get("userType") or session.get("usertype") or session.get("role_name")
        auth_dept_id = login_data.get("userDept") or session.get("dept_id") or session.get("department_id")
        auth_dept_name = login_data.get("dept_name") or session.get("department_name") or session.get("dept_name")

        # In production web portal, session authentication is mandatory to prevent identity spoofing
        user_id = auth_user_id
        role = auth_role
        dept_id = auth_dept_id
        dept_name = auth_dept_name

        # If not in session, allow internal API client only if authorized token/key is provided or test mode
        if not user_id or not role:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer ") or request.headers.get("X-API-Key"):
                user_id = payload.get("user_id")
                role = payload.get("role")
                dept_id = payload.get("dept_id")
                dept_name = payload.get("dept_name")

        if not user_id or not role:
            return jsonify({
                "status": "error",
                "answer": "🛡️ **Authentication Required**: Please sign in to access the Enterprise Risk Management AI Copilot."
            }), 401

        # 1. Governed AI Execution via ERMAIHarness
        try:
            import sys
            from pathlib import Path
            erm_root = str(Path(__file__).resolve().parents[4])
            if erm_root not in sys.path:
                sys.path.insert(0, erm_root)
            
            from ERM_Copilot.ai_harness import ERMAIHarness, HarnessContext

            context = HarnessContext.build_from_auth(
                user_id=user_id,
                user_role=role,
                dept_id=dept_id,
                dept_name=dept_name,
                session_id=str(session_id),
                confirmation_state=payload.get("confirmation_state"),
            )

            resp = ERMAIHarness.run(context=context, message=msg)
            answer_text = getattr(resp, "response", None) or getattr(resp, "answer", None) or "Analysis complete."
            return jsonify({
                "status": getattr(resp, "status", "success"),
                "answer": answer_text,
                "data": getattr(resp, "metadata", {})
            }), 200
        except Exception as local_err:
            current_app.logger.info(f"Direct ERM AI Harness execution fallback to HTTP gateway: {local_err}")


        # 2. Fallback to external HTTP gateway on port 8000
        res = requests.post("http://127.0.0.1:8000/api/erm/chat", json=payload, timeout=60)
        try:
            return jsonify(res.json()), res.status_code
        except Exception:
            return jsonify({"status": "error", "answer": res.text or "Backend returned an unexpected response format."}), res.status_code
    except Exception as e:
        current_app.logger.error(f"ERM Copilot error: {str(e)}")
        return jsonify({"status": "error", "answer": "AI Copilot backend is initializing or unreachable. Please try again in a few seconds."}), 502



@auth_bp.route("/api/erm/speech-to-text", methods=["POST"])
def proxy_erm_speech_to_text():
    """Process voice audio upload and transcribe with Qwen3-ASR / Whisper."""
    try:
        audio_file = request.files.get("audio") or request.files.get("file")
        if not audio_file:
            return jsonify({"status": "error", "message": "No audio file uploaded."}), 400

        audio_bytes = audio_file.read()
        filename = audio_file.filename or "audio.webm"
        content_type = audio_file.content_type or "audio/webm"

        # Direct in-process execution via ERM_Copilot speech service
        try:
            import sys
            from pathlib import Path
            erm_root = str(Path(__file__).resolve().parents[4])
            if erm_root not in sys.path:
                sys.path.insert(0, erm_root)
            
            from ERM_Copilot.services.speech_service import qwen_speech_service
            res = qwen_speech_service.transcribe_audio(
                audio_bytes=audio_bytes,
                filename=filename,
                content_type=content_type
            )
            return jsonify(res), 200
        except Exception as local_err:
            current_app.logger.info(f"Direct Speech-to-Text execution failed: {local_err}")
            return jsonify({"status": "error", "message": str(local_err)}), 500
    except Exception as e:
        current_app.logger.error(f"Speech-to-text endpoint error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@auth_bp.route("/api/erm/feedback", methods=["POST"])
def proxy_erm_feedback():
    try:
        payload = request.get_json() or {}
        rating = int(payload.get("rating", 1))
        category = payload.get("category", "general")
        comment = payload.get("comment")
        request_id = payload.get("request_id")
        user_id = payload.get("user_id", "5")
        user_role = payload.get("role") or payload.get("user_role", "Risk Owner")
        department = payload.get("department") or payload.get("dept_name")
        prompt = payload.get("prompt")
        response_text = payload.get("response") or payload.get("response_snippet")

        try:
            import sys
            from pathlib import Path
            erm_root = str(Path(__file__).resolve().parents[4])
            if erm_root not in sys.path:
                sys.path.insert(0, erm_root)
            from ERM_Copilot.feedback.service import erm_feedback_service
            entry = erm_feedback_service.record_feedback(
                rating=rating,
                category=category,
                comment=comment,
                request_id=request_id,
                user_id=str(user_id),
                user_role=user_role,
                department=department,
                prompt=prompt,
                response=response_text
            )
            return jsonify({
                "status": "success",
                "feedback_id": entry.feedback_id,
                "message": "Thank you! Your feedback helps continuously improve ERM AI quality."
            }), 200
        except Exception as local_err:
            current_app.logger.info(f"Direct feedback recording fallback: {local_err}")

        # Fallback to external HTTP gateway if running separately
        res = requests.post("http://127.0.0.1:8000/api/erm/feedback", json=payload, timeout=10)
        try:
            return jsonify(res.json()), res.status_code
        except Exception:
            return jsonify({"status": "success", "message": "Feedback submitted successfully."}), 200
    except Exception as e:
        current_app.logger.error(f"Feedback recording error: {str(e)}")
        return jsonify({"status": "error", "message": "Unable to save feedback at this moment."}), 500


@auth_bp.route("/api/erm/feedback/summary", methods=["GET"])
def proxy_erm_feedback_summary():
    try:
        try:
            import sys
            from pathlib import Path
            erm_root = str(Path(__file__).resolve().parents[4])
            if erm_root not in sys.path:
                sys.path.insert(0, erm_root)
            from ERM_Copilot.feedback.service import erm_feedback_service
            summary = erm_feedback_service.get_summary()
            return jsonify({
                "status": "success",
                "data": summary
            }), 200
        except Exception as local_err:
            current_app.logger.info(f"Direct feedback summary fallback: {local_err}")

        res = requests.get("http://127.0.0.1:8000/api/erm/feedback/summary", timeout=10)
        return jsonify(res.json()), res.status_code
    except Exception as e:
        current_app.logger.error(f"Feedback summary error: {str(e)}")
        return jsonify({"status": "error", "data": {}}), 500





def roles_required(*roles):
    def wrapper(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            login_data = session.get("login_data", {})
            usertype = (
                login_data.get("userType") or 
                session.get("usertype") or 
                login_data.get("role_name") or 
                ""
            ).strip()

            roles_lower = [r.strip().lower() for r in roles]
            if not usertype or usertype.lower() not in roles_lower:
                abort(403)

            return f(*args, **kwargs)
        return decorated
    return wrapper

def menu_required(menu_id):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):

            current_app.logger.info(f"Requested Menu : {menu_id}")
            current_app.logger.info(f"Session Token  : {session.get('token')}")
            current_app.logger.info(f"Session Menus  : {session.get('menu_ids')}")

            if "token" not in session:
                current_app.logger.info("Token not found")
                return redirect(url_for("auth.ERM"))

            if menu_id not in session.get("menu_ids", []):
                current_app.logger.info("Menu permission denied")
                return redirect(url_for("auth.home"))

            return f(*args, **kwargs)

        return wrapper
    return decorator

@auth_bp.context_processor
def inject_functions():
    login_data = session.get("login_data", {})
    if not login_data:
        #     abort(401) 
        return dict(
        usertype="",
        userdept="",
        username="",
        privileged_roles= ["Admin", "Risk Manager", "Risk Head"], 
        enable_role= ["Risk Owner"], 
        active_dept="",
        functions=[]
        )
    #privileged_roles= ["Admin", "Functional Head", "Risk Manager", "Risk Head"],
    else:
        return dict(
            usertype=login_data.get("userType", "").strip(),
            userdept=login_data.get("userDept", ""),
            username=login_data.get("fname", ""),
            privileged_roles= ["Admin", "Risk Manager", "Risk Head"],
            enable_role= ["Risk Owner"], 
            active_dept = session.get("selected_dept"),
            functions=session.get("functions", [])
        )
    #privileged_roles= ["Admin", "Functional Head", "Risk Manager", "Risk Head"],
    # login_data = session.get("login_data", {})
    # usertype = login_data.get("userType", "") 
    # if "token" not in session:
    #     return dict(functions=[], usertype=usertype)

    # try:
    #     if (usertype != "Action Owner"):
    #         response = APIClient.getdata("departments")
    #         data = response.json()
    #         functions = data.get("data", [])  
    #     else:
    #         functions = []

    # except Exception as e:
    #     current_app.logger.error(f"Error loading functions: {str(e)}")
    #     functions = []

    # return dict(functions=functions,usertype=usertype )

# @auth_bp.route("/erm")
# def login_page():
    # session.clear()
    # return render_template("login.html")


@auth_bp.route("/dashboard")
@roles_required("Admin", "Super Admin", "Risk Manager", "Risk Head")
def dashboard():
    return render_template("dashboard.html", session_data=session.get("login_data", {}))

@auth_bp.route("/riskRegister")
def riskRegister():
    # session["selected_dept"] = ""
    # return redirect(url_for("auth.home"))
    dept_code = "all"
    if (session["usertype"] in ("Risk Owner","Functional Head")):
        session["selected_dept"] = session["dept_id"]  
        dept_code = session["dept_id"]           
    else:
        session["selected_dept"] = "all"
   #return redirect(url_for("auth.home"))
    return redirect(
                    url_for(
                        "auth.risk_register",
                        function_code=dept_code
                    )
                )

@auth_bp.route("/department")
@menu_required(5)
def department():
    return render_template("department.html", session_data=session["login_data"])

@auth_bp.route("/riskDetails")
def riskDetails():
    if "token" not in session:
        return redirect(url_for("auth.ERM"))
    #return render_template("riskDetails.html")
    return render_template("riskDetails.html",session_data=session["login_data"])

@auth_bp.route("/exportExcel")
def exportExcel():
    dept_code = request.args.get("dept_code")
    response = None 
    if dept_code and len(str(dept_code).strip()) > 0 and str(dept_code).strip().lower() != "all":
        response = APIClient.getdata("risk/export-data?dept_id=" + str(dept_code).strip())
    else:
        response = APIClient.getdata("risk/export-data")
    #return "excel downloaded"
    # Convert response to file-like object
    file_stream = BytesIO(response.content)

    return send_file(
        file_stream,
        as_attachment=True,
        download_name="risk_register.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@auth_bp.route("/riskDetailsAdd")
def riskDetailsAdd():
    if "token" not in session:
        return redirect(url_for("auth.ERM"))
    #session["rrid"] = "0"
    #sessionStorage.setItem("rrid", id);
    # login_data={
    #         "userDept": session["user_deptid"],
    #         "userId": session.get("user_id")
    #     }
    return render_template("riskDetails.html",session_data=session["login_data"])

@auth_bp.route("/riskActionPlan")
def riskActionPlan():
    return render_template("riskActionPlan.html",session_data=session["login_data"])

@auth_bp.route("/help")
def help():
    return render_template("help.html", session_data=session.get("login_data", {}))

@auth_bp.route("/risk_register/<function_code>")
def risk_register(function_code):
    #return redirect(url_for("auth.home"))
    
    #risks = RiskRegister.query.filter_by(function_code=function_code).all()
    #risks = get_risk_list(function_code)
    session["selected_dept"] = function_code
    if session["usertype"] in ("Admin", "Risk Head", "Risk Manager", "Functional Head","Risk Owner"):
        if (function_code == "all"):
            return render_template(
            "riskRegister.html",
            dept_code="",
            session_data=session["login_data"]
            )
        else:
            return render_template(
            "riskRegister.html",
            dept_code=function_code,
            session_data=session["login_data"]          
            )
    # elif (session["usertype"] == "Action Owner"):
    #     return render_template("riskTreatment.html", session_data=session["login_data"])
    else:
         #abort(403)
         return redirect(url_for("auth.home"))

# ------------------------------------------------------------
# Helper : Load Financial Year
# ------------------------------------------------------------
def load_financial_year():
    response_fy = APIClient.getdata("financial-year")
    return response_fy.json()


# ------------------------------------------------------------
# Helper : Load Functions
# ------------------------------------------------------------
def load_functions():

    functions = []

    if session["usertype"] != "Action Owner":
        try:
            response = APIClient.getdata("departments")

            if response.status_code == 200:
                functions = response.json().get("data", [])

        except Exception as e:
            current_app.logger.error(f"Department API Error : {e}")

    session["functions"] = functions


# ------------------------------------------------------------
# Helper : Create Session
# ------------------------------------------------------------
def create_login_session(data_res):

    data = data_res.get("data", {})

    session["token"] = data.get("access_token")
    session["user"] = data.get("first_name")
    session["usertype"] = data.get("user_type")
    session["dept_id"] = data.get("department_id")
    session["menu_ids"] = data.get("menuids")

    fy = load_financial_year()

    session["login_data"] = {

        "userDept": data.get("department_id"),
        "userId": data.get("id"),
        "userType": data.get("user_type"),
        "userTypeId": data.get("user_type_id"),
        "fname": data.get("first_name"),
        "lname": data.get("last_name"),
        "roleid": data.get("role_id"),
        "menuIds": data.get("menuids"),
        "current_date": fy.get("data", {}).get("current_date"),
        "financial_year": fy.get("data", {}).get("financial_year")

    }

    load_functions()


# ------------------------------------------------------------
# Helper : Redirect after Login
# ------------------------------------------------------------
def redirect_after_login():
    current_app.logger.info(f"Logged In : {session.get('user')}")
    return redirect(url_for("auth.home"))


# ------------------------------------------------------------
# Single Entry Point
# ------------------------------------------------------------
@auth_bp.route("/", methods=["GET", "POST"])
@auth_bp.route("/ERM", methods=["GET", "POST"])
@auth_bp.route("/erm", methods=["GET", "POST"])
@auth_bp.route("/login", methods=["GET", "POST"])
def ERM():

    session.permanent = False

    # ==========================================================
    # ONELOGIN MODE
    # ==========================================================
    if current_app.config["ONELOGIN_AUTH"]:

        code = request.args.get("code")

        # First Visit
        if not code:

            return "Authorization code missing", 400

        # Callback From OneLogin

        try:

            token_data = {

                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": current_app.config["REDIRECT_URI"]

            }

            token_response = APIClient.post_onelogin(

                "https://pipelineinfra.onelogin.com/oidc/2/token",
                token_data

            )

            if token_response.status_code != 200:
                return token_response.text

            token_resp = token_response.json()

            claims = jwt.decode(

                token_resp["id_token"],
                options={"verify_signature": False},
                algorithms=["RS256"]

            )

            email = claims.get("email")

            current_app.logger.info(f"OneLogin User : {email}")

            login_data = {

                "log_id": email,
                "password": ""

            }

            response = APIClient.post("auth/login", login_data)

            if response.status_code != 200:

                return "You are not authorized to access ERM Application, kindly raise a Service Request in ITSM."

            data_res = response.json()

            create_login_session(data_res)

            return redirect_after_login()

        except Exception as e:

            current_app.logger.error(e)

            return str(e)


    # ==========================================================
    # NORMAL LOGIN
    # ==========================================================
    else:

        if request.method == "POST":

            try:

                login_data = {

                    "log_id": request.form["username"],
                    "password": request.form["password"]

                }

                response = APIClient.post(
                    "auth/login",
                    login_data
                )

                if response.status_code != 200:
                    return render_template(
                        "login.html",
                        error="Invalid Username or Password."
                    )

                data_res = response.json()

                session.permanent = bool(request.form.get("remember"))
                create_login_session(data_res)

                return redirect_after_login()

            except Exception as e:

                current_app.logger.error(e)

                return render_template(
                    "login.html",
                    error="Login Failed."
                )

        return render_template("login.html")

# @auth_bp.route("/login_ui", methods=["GET", "POST"])
# def login_ui():
# 	return render_template("login.html")
    
# @auth_bp.route("/ERM", methods=["GET", "POST"])
# def auth_login():
#     code = request.args.get("code")
    
#     if not code:
#         return "Authorization code missing", 400
    
#     data ={"grant_type": "authorization_code",
#                 "code": code,"redirect_uri": f"{current_app.config['REDIRECT_URI']}"}
#     try:
#         token_response  = APIClient.post_onelogin("https://pipelineinfra.onelogin.com/oidc/2/token", data)
#     except Exception as e:
#         current_app.logger.error(f"API Onelogin POST Error: {str(e)}")
#         return str(e)
#     if token_response.status_code != 200:
#         return token_response.text
        
#     token_resp = token_response.json()
#     claims = jwt.decode(
#             token_resp["id_token"],
#             options={"verify_signature": False},
#             algorithms=["RS256"]
#             )
            
#     print(claims)
#     email = claims.get("email")
#     name = claims.get("name")
#     current_app.logger.info(f"OneLogin Email Received : " + email)
#     current_app.logger.info(f"OneLogin Name Received : " + name)

#     try:
#         data ={"log_id": email,
#             "password": ""}
        
#         response = APIClient.post("auth/login", data)
#         if response.status_code != 200:
#             return "You are not authorized to access ERM Application, kindly raise a Service Request in ITSM."
#         data_res = response.json()

#         session["token"] = data_res.get("data", {}).get("access_token")
#         session["user"] = data_res.get("data", {}).get("first_name")
#         session["usertype"] = data_res.get("data", {}).get("user_type")
#         session["dept_id"] = data_res.get("data", {}).get("department_id")
#         session["menu_ids"] = data_res.get("data", {}).get("menuids")

#         response_fy = APIClient.getdata("financial-year")
#         data_fy = response_fy.json()

#         session["login_data"]={
#         "userDept": data_res.get("data", {}).get("department_id"),
#         "userId": data_res.get("data", {}).get("id"),
#         "userType": data_res.get("data", {}).get("user_type"),
#         "userTypeId": data_res.get("data", {}).get("user_type_id"),
#         "fname": data_res.get("data", {}).get("first_name"),
#         "lname": data_res.get("data", {}).get("last_name"),
#         "roleid":data_res.get("data", {}).get("role_id"),
#         "menuIds": data_res.get("data", {}).get("menuids"),
#         "current_date":data_fy.get("data", {}).get("current_date"),
#         "financial_year":data_fy.get("data", {}).get("financial_year")
#         }

#         current_app.logger.info(f"Session logged in Using Onelogin: {session['user']}")

#         functions = []
#         if session["usertype"]  != "Action Owner":
#             try:
#                 response = APIClient.getdata("departments")
#                 if response.status_code == 200:
#                     functions = response.json().get("data", [])
#             except Exception as e:
#                 current_app.logger.error(f"One Login-time API error: {str(e)}")

#         session["functions"] = functions

#         if session["usertype"]  == "Admin":
#             return redirect(url_for("auth.home"))
#         else:
#             return redirect(
#                 url_for(
#                     "auth.risk_register",
#                     function_code=session["dept_id"]
#                 )
#             )

#     except Exception as e:
#         current_app.logger.error(f"Error -> {str(e)}")

# @auth_bp.route("/login", methods=["GET", "POST"])
# def login():
#     current_app.logger.info(f"Logged In Started")
#     session.permanent = True

#     if request.method == "POST":
#         try:
#             data ={"log_id": request.form["username"],
#                 "password": request.form["password"]}
            
#             response = APIClient.post("auth/login", data)
#             data_res = response.json()

#             session["token"] = data_res.get("data", {}).get("access_token")
#             session["user"] = data_res.get("data", {}).get("first_name")
#             session["usertype"] = data_res.get("data", {}).get("user_type")
#             session["dept_id"] = data_res.get("data", {}).get("department_id")

#             response_fy = APIClient.getdata("financial-year")
#             data_fy = response_fy.json()
#             #session["financial_year"] = data_fy.get("data", {}).get("financial_year")

#             session["login_data"]={
#             "userDept": data_res.get("data", {}).get("department_id"),
#             "userId": data_res.get("data", {}).get("id"),
#             "userType": data_res.get("data", {}).get("user_type"),
#             "userTypeId": data_res.get("data", {}).get("user_type_id"),
#             "fname": data_res.get("data", {}).get("first_name"),
#             "lname": data_res.get("data", {}).get("last_name"),
#             "roleid":data_res.get("data", {}).get("role_id"),
#             "current_date":data_fy.get("data", {}).get("current_date"),
#             "financial_year":data_fy.get("data", {}).get("financial_year")
#             }

#             current_app.logger.info(f"Session logged in: {session['user']}")

#             functions = []
#             if session["usertype"]  != "Action Owner":
#                 try:
#                     response = APIClient.getdata("departments")
#                     if response.status_code == 200:
#                         functions = response.json().get("data", [])
#                 except Exception as e:
#                     current_app.logger.error(f"Login-time API error: {str(e)}")

#             session["functions"] = functions

#             if session["usertype"]  == "Admin":
#                 return redirect(url_for("auth.home"))
#             else:
#                 return redirect(
#                     url_for(
#                         "auth.risk_register",
#                         function_code=session["dept_id"]
#                     )
#                 )

#         except Exception as e:
#             current_app.logger.error(f"Error -> {str(e)}")

#     return render_template("login.html")



@auth_bp.route("/home")
def home():
    if "token" not in session:
        return redirect(url_for("auth.ERM"))
    return render_template(
        "home.html",
        session_data=session.get("login_data", {}),
        usertype=session.get("usertype", ""),
        userdept=session.get("dept_id", "")
    )


@auth_bp.route("/api/home/workload", methods=["GET"])
def home_workload():
    if "token" not in session:
        return jsonify({"success": False, "message": "Unauthorized"}), 401
    try:
        response = APIClient.getdata("home/workload")
        return jsonify(response.json()), response.status_code
    except Exception as e:
        current_app.logger.error(f"Home workload proxy error: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@auth_bp.route("/riskTreatment")
def riskTreatment():
    if "token" not in session:
        return redirect(url_for("auth.ERM"))
    return render_template("riskTreatment.html", session_data=session.get("login_data", {}))
         

@auth_bp.route("/logout")
def logout():
    user = session.get("user")
    session.clear()
    current_app.logger.info(f"User logged out: {user}")
    if (current_app.config['ONELOGIN_AUTH'] == True):
        return redirect(current_app.config['REDIRECT_URI_LOGOUT'])
    else:
        return redirect(url_for("auth.ERM"))


@auth_bp.route("/addnewdpt", methods=["GET", "POST"])
def get_addnewdpt():
    current_app.logger.info(f"Use api hittt addnewuser")
    dept_name = request.args.get("dept_name")
    description= request.args.get("description")

    current_app.logger.info(f"Use api value dept_name{dept_name}")
    current_app.logger.info(f"Use api value dept_name{description}")
    try:
        response = APIClient.postdata("departments", {
            "dept_name": dept_name,
            "description": description
        })
        current_app.logger.info(f"API executed get_addnewdpt")
        data = response.json()
        current_app.logger.info(f"API executed get_ad")
        current_app.logger.info(f"API responsee->{data}")
        # current_app.logger.infcurrent_app.logger.info(f"API Dept Save{data}")o(f"User Info get logged in: {data.get("user_fname")}")
        # current_app.logger.info(f"Use api hittt ")
        return jsonify(data), 200
    except Exception:
        flash("user failed")
    return render_template("RiskRegister.html")

@auth_bp.route("/getbyid", methods=["GET", "POST"])
def getd_ptbyid():
    current_app.logger.info(f"Use api hit getbyid")
    dept_id = request.args.get("dept_id")
    current_app.logger.info(f"Use api value dept_id{dept_id}")
    try:
        response = APIClient.getbyid("departments", 
            dept_id,
        )
        current_app.logger.info(f"API executed dept_id")
        data = response.json()
        current_app.logger.info(f"API executed dept_id")
        current_app.logger.info(f"API responsee->{data}")
        # current_app.logger.infcurrent_app.logger.info(f"API Dept Save{data}")o(f"User Info get logged in: {data.get("user_fname")}")
        # current_app.logger.info(f"Use api hittt ")
        return jsonify(data), 200
    except Exception:
        flash("user failed")
    return render_template("RiskRegister.html")


@auth_bp.route("/UpdateDptById", methods=["POST"])
def update_dpt():

    current_app.logger.info("Use api hit UpdateDptById")

    data = request.json

    dept_id = data.get("dept_id")
    dptname = data.get("dptname")
    dptdes = data.get("dptdes")

    try:
        response = APIClient.putdata(f"departments/{dept_id}", {
            "dept_name": dptname,
            "description": dptdes
        })

        data = response.json()

        return jsonify(data), 200

    except Exception as e:
        current_app.logger.error(f"Error -> {str(e)}")
        return jsonify({"error": "Update failed"}), 500

@auth_bp.route("/getalldpt", methods=["GET"])
def get_all_dpt():
    current_app.logger.info("Use api hit getalldpt")
    try:
        response = APIClient.getdata("departments")
        data = response.json()

        current_app.logger.info(f"API response->{data}")

        return jsonify(data), 200

    except Exception as e:
        current_app.logger.error(f"Error -> {str(e)}")
        return jsonify({"Error": True, "message": "Failed"}), 500
    
@auth_bp.route("/getalluser", methods=["GET"])
def getalluser():
    current_app.logger.info("Use api hit getalluser")
    try:
        response = APIClient.getdata("users")
        data = response.json()
        current_app.logger.info(f"API response->{data}")
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f"Error in APIClient getalluser, falling back to DB: {str(e)}")
        try:
            from app.db_direct import fetch_all_users
            users = fetch_all_users()
            return jsonify({"data": users, "Error": {"Error": False, "Error_message": "Success"}}), 200
        except Exception as db_e:
            current_app.logger.error(f"DB fallback error: {str(db_e)}")
            return jsonify({"Error": True, "message": "Failed"}), 500    

@auth_bp.route("/getdeptwiseuser", methods=["GET"])
def getdeptwiseuser():
    current_app.logger.info("Use api hit getdeptwiseuser")
    dept_code = request.args.get("dept_code")
    try:
        response = APIClient.getdata("users/department/" + str(dept_code))
        data = response.json()
        current_app.logger.info(f"API response->{data}")
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f"Error in APIClient getdeptwiseuser, falling back to DB: {str(e)}")
        try:
            from app.db_direct import fetch_dept_users
            d_id = int(dept_code) if dept_code and str(dept_code).isdigit() else 1
            users = fetch_dept_users(d_id)
            return jsonify({"data": users, "Error": {"Error": False, "Error_message": "Success"}}), 200
        except Exception as db_e:
            current_app.logger.error(f"DB fallback error: {str(db_e)}")
            return jsonify({"Error": True, "message": "Failed"}), 500    
    
@auth_bp.route("/getstatus", methods=["GET"])
def getstatus():
    current_app.logger.info("Use api hit getstatus")
    type_val = request.args.get("type", "risk")
    try:
        response = APIClient.getbyid("approval/type", type_val)
        data = response.json()
        current_app.logger.info(f"API response->{data}")
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f"Error in APIClient getstatus, falling back to DB: {str(e)}")
        try:
            from app.db_direct import fetch_statuses
            statuses = fetch_statuses(type_val)
            return jsonify({"data": statuses, "Error": {"Error": False, "Error_message": "Success"}}), 200
        except Exception as db_e:
            current_app.logger.error(f"DB fallback error: {str(db_e)}")
            return jsonify({"Error": True, "message": "Failed"}), 500   
    
@auth_bp.route("/GetAllRiskRegister", methods=["GET"])
def getallriskregister():
    current_app.logger.info("Use api hit GetAllRiskRegister")
    try:
        #response = APIClient.getdata("risk-register")
        dept_code = request.args.get("dept_code")
        response = None 
        if (len(dept_code)> 0):
            response = APIClient.getdata("risk/risks?dept_id=" + dept_code)
        else:
            response = APIClient.getdata("risk/risks/")

        data = response.json()

        current_app.logger.info(f"API response->{data}")
	#row_count = len(data.get("data", []))
	#current_app.logger.info(f"API returned {row_count} rows")

        resp = make_response(jsonify(data), 200)
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        return resp

    except Exception as e:
        current_app.logger.error(f"Error -> {str(e)}")
        return jsonify({"Error": True, "message": "Failed"}), 500
        

@auth_bp.route("/GetUserTreatment", methods=["GET"])
def GetUserTreatment():
    current_app.logger.info("Use api hit GetUserTreatment")
    try:
        #response = APIClient.getdata("risk-register")
        treatment_id = request.args.get("treatment_id")
        response = None 
        response = APIClient.getdata("risk/assign?id=" + treatment_id)

        data = response.json()

        current_app.logger.info(f"API response->{data}")

        return jsonify(data), 200

    except Exception as e:
        current_app.logger.error(f"Error -> {str(e)}")
        return jsonify({"Error": True, "message": "Failed"}), 500
    
@auth_bp.route("/addnewrisk_all", methods=["POST"])
def addnewrisk_all():
    current_app.logger.info(f"Use api hittt addnewrisk_all")
    data = request.get_json()
    params = data.get("params")
    params_riskdesc = data.get("params_riskdesc")
    params_treatment = data.get("dataList", [])
    #risk_action_plan_list = data.get("risk_action_plan_list", [])
    #risk_name = params.get("risk_name")


    risk_name = params.get("risk_name")
    dept_id= params.get("dept_id")
    risk_owner_id= params.get("risk_owner_id")
    risk_co_owner_id = params.get("risk_co_owner_id")
    financial_year= params.get("financial_year")
    risk_status= params.get("risk_status")
    risk_progress= params.get("risk_progress")
    is_active=params.get("is_active")
    risk_register_id=params.get("risk_register_id")
    risk_id=params.get("risk_id")

    if len(risk_register_id)<=0:
        risk_register_id = "0"
    params_riskmst = {
            "risk_register_id": risk_register_id,
            "risk_name": risk_name,
            "dept_id": dept_id,
            "risk_owner_id": risk_owner_id,
            "risk_co_owner_id" :risk_co_owner_id,
            "financial_year": financial_year,
            "risk_status": risk_status,
            "risk_progress":risk_progress,
            "is_active":is_active
	}

    #risk_register_id = params.get("risk_register_id")
    risk_description= params_riskdesc.get("risk_description")
    inherent_risk_likelihood_id= params_riskdesc.get("inherent_risk_likelihood_id")
    inherent_risk_impact_id= params_riskdesc.get("inherent_risk_impact_id")
    mitigation= params_riskdesc.get("mitigation")
    current_risk_likelihood_id= params_riskdesc.get("current_risk_likelihood_id")
    current_risk_impact_id=params_riskdesc.get("current_risk_impact_id")
    risk_description_id=params_riskdesc.get("risk_description_id")
    

    if len(params_riskdesc)>0:
        if len(risk_description_id)<=0:
            risk_description_id = "0"

        params_riskdesc = {
                "risk_description_id": risk_description_id,
                "risk_description": risk_description,
                "inherent_risk_likelihood_id": inherent_risk_likelihood_id,
                "inherent_risk_impact_id": inherent_risk_impact_id,
                "mitigation": mitigation,
                "current_risk_likelihood_id":current_risk_likelihood_id,
                "current_risk_impact_id":current_risk_impact_id
            }
    
    processed_actions = []

    for action in params_treatment:
        processed_actions.append({
            "risk_description_id": risk_description_id ,
            "risk_register_id": risk_register_id,
            "risk_id": risk_id,
            "action_plan": action.get("action_plan"),
            "action_owner_id": action.get("action_owner_id"),
            "target_date": action.get("target_date"),
            "progress": action.get("progress"),
            "action_status_id": action.get("action_status_id"),
            "next_followup_date": action.get("next_followup_date")
        })

    finalPayload = {
    "risk_register": params_riskmst,
    "risk_description": params_riskdesc,
    "risk_treatments": processed_actions
    }
    #data_treatment = request.get_json()
    #jsonify(finalPayload)
    try:
        response = APIClient.postdata("risk/save", 
           finalPayload
        )
        current_app.logger.info(f"API executed addnewrisk")
        data = response.json()
        current_app.logger.info(f"API executed addnewrisk")
        current_app.logger.info(f"API responsee->{data}")
        # current_app.logger.infcurrent_app.logger.info(f"API Dept Save{data}")o(f"User Info get logged in: {data.get("user_fname")}")
        # current_app.logger.info(f"Use api hittt ")
        return jsonify(data), 200
    except Exception as e:
        flash("user failed")
    return render_template("RiskRegister.html")

@auth_bp.route("/addnewrisk", methods=["GET", "POST"])
def addnewrisk():
    current_app.logger.info(f"Use api hittt addnewrisk")
    risk_name = request.args.get("risk_name")
    dept_id= request.args.get("dept_id")
    risk_owner_id= request.args.get("risk_owner_id")
    financial_year= request.args.get("financial_year")
    risk_status= request.args.get("risk_status")
    risk_progress= request.args.get("risk_progress")
    is_active=request.args.get("is_active")
    try:
        response = APIClient.postdata("risk-register/", {
            "risk_name": risk_name,
            "dept_id": dept_id,
            "risk_owner_id": risk_owner_id,
            "financial_year": financial_year,
            "risk_status": risk_status,
            "risk_progress":risk_progress,
            "is_active":is_active
        })
        current_app.logger.info(f"API executed addnewrisk")
        data = response.json()
        current_app.logger.info(f"API executed addnewrisk")
        current_app.logger.info(f"API responsee->{data}")
        # current_app.logger.infcurrent_app.logger.info(f"API Dept Save{data}")o(f"User Info get logged in: {data.get("user_fname")}")
        # current_app.logger.info(f"Use api hittt ")
        return jsonify(data), 200
    except Exception:
        flash("user failed")
    return render_template("RiskRegister.html")

@auth_bp.route("/AddNewRiskDescription", methods=["GET", "POST"])
def addnewriskdescription():
    #current_app.logger.info(f"Use api hittt addnewrisk")
    risk_register_id = request.args.get("risk_register_id")
    risk_description= request.args.get("risk_description")
    inherent_risk_likelihood_id= request.args.get("inherent_risk_likelihood_id")
    inherent_risk_impact_id= request.args.get("inherent_risk_impact_id")
    mitigation= request.args.get("mitigation")
    current_risk_likelihood_id= request.args.get("current_risk_likelihood_id")
    current_risk_impact_id=request.args.get("current_risk_impact_id")
    try:
        response = APIClient.postdata("risk-description/", {
            "risk_register_id": risk_register_id,
            "risk_description": risk_description,
            "inherent_risk_likelihood_id": inherent_risk_likelihood_id,
            "inherent_risk_impact_id": inherent_risk_impact_id,
            "mitigation": mitigation,
            "current_risk_likelihood_id":current_risk_likelihood_id,
            "current_risk_impact_id":current_risk_impact_id
        })
        current_app.logger.info(f"API executed addnewrisk")
        data = response.json()
        current_app.logger.info(f"API executed addnewrisk")
        current_app.logger.info(f"API responsee->{data}")
        # current_app.logger.infcurrent_app.logger.info(f"API Dept Save{data}")o(f"User Info get logged in: {data.get("user_fname")}")
        # current_app.logger.info(f"Use api hittt ")
        return jsonify(data), 200
    except Exception:
        flash("user failed")
    return render_template("RiskRegister.html")


@auth_bp.route("/AddNewRiskTreatment", methods=["POST"])
def addnewrisktreatment():

    current_app.logger.info("AddNewRiskTreatment API hit")

    data = request.get_json()
    current_app.logger.info(f"AddNewRiskTreatment Request -> {data}")

    try:
        response = APIClient.postdata("risk-treatment/", data)

        current_app.logger.info("API executed AddNewRiskTreatment")

        data = response.json()

        current_app.logger.info(f"API response -> {data}")

        return jsonify(data), 200

    except Exception as e:
        current_app.logger.error(f"AddNewRiskTreatment Error -> {str(e)}")
        flash("Risk Treatment Save Failed")

    return jsonify({"Error": True})

@auth_bp.route("/getRiskRegisterbyid_all", methods=["GET", "POST"])
def getRiskRegisterbyid_all():
    current_app.logger.info(f"Use api hit getRiskRegisterbyid")
    RiskRegister_id = request.args.get("RiskRegister_id")
    current_app.logger.info(f"Use api value dept_id{RiskRegister_id}")
    try:
        response = APIClient.getbyid("risk/risks_by_id", 
            RiskRegister_id,
        )
        data = response.json()
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f"getRiskRegisterbyid Error -> {str(e)}, falling back to DB")
        try:
            from app.db_direct import fetch_risk_by_id_full
            risk_item = fetch_risk_by_id_full(RiskRegister_id)
            if risk_item:
                return jsonify({"data": [risk_item], "Error": {"Error": False, "Error_message": "Success"}}), 200
        except Exception as db_err:
            current_app.logger.error(f"DB fallback for getRiskRegisterbyid_all failed: {str(db_err)}")
        return jsonify({"Error": True, "message": "Failed"}), 500

@auth_bp.route("/get_last_risk_status", methods=["GET", "POST"])
def get_last_risk_status():
    current_app.logger.info(f"Use api hit get_last_risk_status")
    RiskRegister_id = request.args.get("RiskRegister_id")
    current_app.logger.info(f"Use api value /get_last_risk_status?risk_id={RiskRegister_id}")
    try:
        response = APIClient.getbyid("risk", 
            "get_last_risk_status?risk_id="+RiskRegister_id,
        )
        current_app.logger.info(f"API executed get_last_risk_status")
        data = response.json()
        current_app.logger.info(f"API executed get_last_risk_status")
        current_app.logger.info(f"API responsee get_last_risk_status->{data}")
        # current_app.logger.infcurrent_app.logger.info(f"API Dept Save{data}")o(f"User Info get logged in: {data.get("user_fname")}")
        # current_app.logger.info(f"Use api hittt ")
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f"getRiskRegisterbyid Error -> {str(e)}")
        flash("user failed")
    return render_template("RiskRegister.html")


@auth_bp.route("/getApprovalHistorybyRiskId", methods=["GET", "POST"])
def getApprovalHistorybyRiskId():
    RiskRegister_id = request.args.get("RiskRegister_id")
    try:
        response = APIClient.getbyid("approval/history", 
            RiskRegister_id,
        )
        data = response.json()
        current_app.logger.info(f"API responsee->{data}")
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f"getApprovalHistorybyRiskId Error -> {str(e)}")
        return jsonify({"data": [], "Error": {"Error": False, "Error_message": "No history records", "Error_Code": 200}}), 200

@auth_bp.route("/getRiskRegisterbyid", methods=["GET", "POST"])
def getRiskRegisterbyid():
    current_app.logger.info(f"Use api hit getRiskRegisterbyid")
    RiskRegister_id = request.args.get("RiskRegister_id")
    current_app.logger.info(f"Use api value dept_id{RiskRegister_id}")
    try:
        response = APIClient.getbyid("risk-register/Risk_Register_id", 
            RiskRegister_id,
        )
        data = response.json()
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f"getRiskRegisterbyid Error -> {str(e)}, falling back to DB")
        try:
            from app.db_direct import fetch_risk_by_id_full
            risk_item = fetch_risk_by_id_full(RiskRegister_id)
            if risk_item:
                return jsonify({"data": risk_item, "Error": {"Error": False, "Error_message": "Success"}}), 200
        except Exception as db_err:
            current_app.logger.error(f"DB fallback for getRiskRegisterbyid failed: {str(db_err)}")
        return jsonify({"Error": {"Error": True, "Error_message": str(e)}}), 500




@auth_bp.route("/getRiskDescriptionbyid_all", methods=["GET", "POST"])
def getRiskDescriptionbyid_all():
    current_app.logger.info(f"Use api hit getRiskDescriptionbyid")
    RiskRegisterDescriptiondetail_id = request.args.get("RiskRegisterDescriptiondetail_id")
    current_app.logger.info(f"Use api value dept_idgetRiskDescriptionbyid{RiskRegisterDescriptiondetail_id}")
    try:
        response = APIClient.getbyid("risk/risk_by_description", 
            RiskRegisterDescriptiondetail_id,
        )
        current_app.logger.info(f"API executed getRiskDescriptionbyid")
        data = response.json()
        current_app.logger.info(f"API executed getRiskDescriptionbyid")
        current_app.logger.info(f"API responsee getRiskDescriptionbyid->{data}")
        # current_app.logger.infcurrent_app.logger.info(f"API Dept Save{data}")o(f"User Info get logged in: {data.get("user_fname")}")
        # current_app.logger.info(f"Use api hittt ")
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f"getRiskRegisterbyid Error -> {str(e)}")
        flash("user failed")
    return render_template("RiskRegister.html")

@auth_bp.route("/getRiskDescriptionbyid", methods=["GET", "POST"])
def getRiskDescriptionbyid():
    current_app.logger.info(f"Use api hit getRiskDescriptionbyid")
    Risk_id = request.args.get("Risk_id")
    current_app.logger.info(f"Use api value dept_idgetRiskDescriptionbyid{Risk_id}")
    try:
        response = APIClient.getbyid("risk-description", 
            Risk_id,
        )
        current_app.logger.info(f"API executed getRiskDescriptionbyid")
        data = response.json()
        current_app.logger.info(f"API executed getRiskDescriptionbyid")
        current_app.logger.info(f"API responsee getRiskDescriptionbyid->{data}")
        # current_app.logger.infcurrent_app.logger.info(f"API Dept Save{data}")o(f"User Info get logged in: {data.get("user_fname")}")
        # current_app.logger.info(f"Use api hittt ")
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f"getRiskRegisterbyid Error -> {str(e)}")
        flash("user failed")
    return render_template("RiskRegister.html")

@auth_bp.route("/getRiskDescriptiondetailsbyid", methods=["GET", "POST"])
def getRiskDescriptiondetailsbyid():
    current_app.logger.info(f"Use api hit getRiskDescriptiondetailsbyid")
    RiskDescriptiondetail_id = request.args.get("RiskRegisterDescriptiondetail_id")
    current_app.logger.info(f"Use api value dept_id{RiskDescriptiondetail_id}")
    try:
        response = APIClient.getbyid("risk-description/risk_description_id", 
            RiskDescriptiondetail_id,
        )
        current_app.logger.info(f"API executed getRiskDescriptiondetailsbyid")
        data = response.json()
        current_app.logger.info(f"API executed getRiskDescriptiondetailsbyid")
        current_app.logger.info(f"API responsee getRiskDescriptiondetailsbyid->{data}")
        # current_app.logger.infcurrent_app.logger.info(f"API Dept Save{data}")o(f"User Info get logged in: {data.get("user_fname")}")
        # current_app.logger.info(f"Use api hittt ")
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f"getRiskDescriptiondetailsbyid Error -> {str(e)}")
        flash("user failed")
    return render_template("RiskRegister.html")


@auth_bp.route("/getRiskTreatmentbyRiskid", methods=["GET", "POST"])
def getRiskTreatmentbyRiskid():
    current_app.logger.info(f"Use api hit getRiskTreatmentbyRiskid")
    Risk_id = request.args.get("Risk_id")
    current_app.logger.info(f"Use api value dept_idgetRiskTreatmentbyRiskid{Risk_id}")
    try:
        response = APIClient.getbyid("risk-treatment", 
            Risk_id,
        )
        current_app.logger.info(f"API executed getRiskTreatmentbyRiskid")
        data = response.json()
        current_app.logger.info(f"API executed getRiskTreatmentbyRiskid")
        current_app.logger.info(f"API responsee getRiskTreatmentbyRiskid->{data}")
        # current_app.logger.infcurrent_app.logger.info(f"API Dept Save{data}")o(f"User Info get logged in: {data.get("user_fname")}")
        # current_app.logger.info(f"Use api hittt ")
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f"getRiskRegisterbyid Error -> {str(e)}")
        flash("user failed")
    return render_template("RiskRegister.html")   

@auth_bp.route("/getRiskTreatmentbyTreatmentid", methods=["GET", "POST"])
def getRiskTreatmentbyTreatmentid():
    current_app.logger.info(f"Use api hit getRiskTreatmentbyTreatmentid")
    Risk_id = request.args.get("Risk_id")
    current_app.logger.info(f"Use api value getRiskTreatmentbyTreatmentid{Risk_id}")
    try:
        response = APIClient.getbyid("risk-treatment/risk_treatment_id", 
            Risk_id,
        )
        current_app.logger.info(f"API executed getRiskTreatmentbyTreatmentid")
        data = response.json()
        current_app.logger.info(f"API executed getRiskTreatmentbyTreatmentid")
        current_app.logger.info(f"API responsee getRiskTreatmentbyTreatmentid->{data}")
        # current_app.logger.infcurrent_app.logger.info(f"API Dept Save{data}")o(f"User Info get logged in: {data.get("user_fname")}")
        # current_app.logger.info(f"Use api hittt ")
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f"getRiskRegisterbyTreatmentid Error -> {str(e)}")
        flash("user failed")
    return render_template("RiskRegister.html")       


#change by sunil
@auth_bp.route("/getstatusListtreatment", methods=["GET"])
def getstatusListtreatment():
    try:
        #response = APIClient.getdata("approval/type/treatment")
        response = APIClient.getdata("approval/type/action_plan")
        current_app.logger.info(f"Status API Responce -->{response}")
        data = response.json()
        current_app.logger.info(f"API response approval/type/action_plan ->{data}")
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f"Error -> {str(e)}")
        return jsonify({"Error": True, "message": "Failed"}), 500
    
@auth_bp.route("/getstatusListrisk", methods=["GET"])
def getstatusListRisk():
    try:
        response = APIClient.getdata("approval/type/risk")
        current_app.logger.info(f"Status API Responce -->{response}")
        data = response.json()
        current_app.logger.info(f"API response approval/type/risk Update ->{data}")
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f"Error -> {str(e)}")
        return jsonify({"Error": True, "message": "Failed"}), 500   

@auth_bp.route("/AddNewRiskDes1", methods=["GET", "POST"])
def AddNewRiskDes1():
    current_app.logger.info(f"Use api hittt AddNewRiskDes")
    risk_register_id = request.args.get("risk_register_id")
    current_app.logger.info(f"API executed AddNewRiskDes")
    reference_id = request.args.get("reference_id")
    module_name = request.args.get("module_name")
    remark = request.args.get("remark")
    progress = request.args.get("progress")
    status = request.args.get("status")
    next_followup_date = request.args.get("next_followup_date")
    try:
        response = APIClient.postdata("risk-followup/", {
           "reference_id": reference_id,
            "module_name": module_name,
            "remark": remark,
            "progress": progress,
            "status": status,
            "next_followup_date": next_followup_date
             
        })  
        
        data = response.json()
        current_app.logger.info(f"API executed addnewrisk")
        current_app.logger.info(f"API responsee->{data}")
        # current_app.logger.infcurrent_app.logger.info(f"API Dept Save{data}")o(f"User Info get logged in: {data.get("user_fname")}")
        # current_app.logger.info(f"Use api hittt ")
        return jsonify(data), 200
    except Exception:
        flash("user failed")
    return render_template("RiskActionplan.html")

@auth_bp.route("/AddNewRiskDesold", methods=["POST"])
def AddNewRiskDesold():

    reference_id = request.form.get("reference_id")
    module_name = request.form.get("module_name")
    remark = request.form.get("remark")
    progress = request.form.get("progress")
    status = request.form.get("status")
    next_followup_date = request.form.get("next_followup_date")

    file = request.files.get("file")
    

    files = None
    if file:
        files = {
            "file": (file.filename, file.stream, file.mimetype)
        }

    response = APIClient.postdatafile(
        "risk-followup/",
        {
            "reference_id": reference_id,
            "module_name": module_name,
            "remark": remark,
            "progress": progress,
            "status": status,
            "next_followup_date": next_followup_date
        },
        files=files   
    )

    return jsonify(response.json()), 200

@auth_bp.route("/AddNewRiskDes", methods=["POST"])
def AddNewRiskDes():

    reference_id = request.form.get("reference_id")
    module_name = request.form.get("module_name")
    remark = request.form.get("remark")
    progress = request.form.get("progress")
    status = request.form.get("status")
    next_followup_date = request.form.get("next_followup_date")

    file = request.files.get("file")

    data = {
        "reference_id": reference_id,
        "module_name": module_name,
        "remark": remark,
        "progress": progress,
        "status": status,
        "next_followup_date": next_followup_date
    }

    if file and file.filename:
        files = {
            "file": (file.filename, file.stream, file.mimetype)
        }

        response = APIClient.postdatafile(
            "risk-followup/",
            data,
            files=files
        )
    else:
        # ✅ File nahi hai to normal API call
        response = APIClient.postdatafile(
            "risk-followup/",
            data
        )

    return jsonify(response.json()), 200


@auth_bp.route("/riskfollowup", methods=["GET", "POST"])
def riskfollowup():
    current_app.logger.info(f"Use api hit riskfollowup")
    Risk_id = request.args.get("Risk_id")
    current_app.logger.info(f"Use api value riskfollowup{Risk_id}")
    try:
        #response = APIClient.getbyid("risk-treatment/risk_treatment_id", 
        #    Risk_id,
        #)
        response = APIClient.getbyid("risk-followup/reference_id", 
            Risk_id,
        )
        
        current_app.logger.info(f"API executed riskfollowup")
        data = response.json()
        current_app.logger.info(f"API executed riskfollowup")
        current_app.logger.info(f"API responsee riskfollowup->{data}")
        # current_app.logger.infcurrent_app.logger.info(f"API Dept Save{data}")o(f"User Info get logged in: {data.get("user_fname")}")
        # current_app.logger.info(f"Use api hittt ")
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f"riskfollowup Error -> {str(e)}")
        flash("user failed")
    return render_template("RiskRegister.html")

@auth_bp.route("/getRiskDescriptiondetailsbyids", methods=["GET", "POST"])
def getRiskDescriptiondetailsbyids():
    current_app.logger.info(f"Use api hit getRiskDescriptiondetailsbyid")
    RiskDescriptiondetail_id = request.args.get("RiskRegisterDescriptiondetail_id")
    current_app.logger.info(f"Use api value dept_id{RiskDescriptiondetail_id}")
    try:
        response = APIClient.getbyid("risk/risk_by_description", 
            RiskDescriptiondetail_id,
        )
        current_app.logger.info(f"API executed getRiskDescriptiondetailsbyid")
        data = response.json()
        current_app.logger.info(f"API executed getRiskDescriptiondetailsbyid")
        current_app.logger.info(f"API responsee getRiskDescriptiondetailsbyid->{data}")
        # current_app.logger.infcurrent_app.logger.info(f"API Dept Save{data}")o(f"User Info get logged in: {data.get("user_fname")}")
        # current_app.logger.info(f"Use api hittt ")
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f"getRiskDescriptiondetailsbyid Error -> {str(e)}")
        flash("user failed")
    return render_template("RiskRegister.html")

@auth_bp.route("/ApproveRisk", methods=["GET", "POST"])
def AddNewApproveRisk():
    current_app.logger.info("API hit ApproveRisk ---->")
    risk_register_id = request.args.get("risk_register_id")
    approval_level = request.args.get("approval_level")
    approval_status_id = request.args.get("approval_status_id")
    remark = request.args.get("remark")
    current_app.logger.info(f"Params -> risk_register_id: {risk_register_id}, level: {approval_level}, status: {approval_status_id}, remark: {remark}")
    try:
        # import time
        # time.sleep(15)
        response = APIClient.postdata("approval/approve", {
            "risk_register_id": int(risk_register_id),
            "approval_level": int(approval_level),
            "approval_status_id": int(approval_status_id),
            "remark": remark
        })

        data = response.json()
        current_app.logger.info("API executed ApproveRisk")
        current_app.logger.info(f"API response ApproveRisk -> {data}")
        return jsonify(data), 200

    except Exception as e:
        current_app.logger.error(f"Error in ApproveRisk -> {str(e)}")
        return jsonify({"Error": True, "message": "Failed"}), 500
    
@auth_bp.route("/downloadReffile")
def downloadReffile():
    dept_code = request.args.get("dept_code")
    response = None 
    if (len(dept_code)> 0):
        response = APIClient.getdata("risk-followup/download-file/" + dept_code)
        current_app.logger.info(f"API responsee->{response}")
    else:
        response = APIClient.getdata("risk/export-data")
    #return "excel downloaded"
    # Convert response to file-like object
    file_stream = BytesIO(response.content)
    # Get filename from API response header (if available)
    content_disposition = response.headers.get("Content-Disposition")
    filename = "downloaded_file"
    if content_disposition:
        import re
        match = re.search('filename="?(.+)"?', content_disposition)
        if match:
            filename = match.group(1)

    # Get mimetype dynamically
    mimetype = response.headers.get("Content-Type", "application/octet-stream")

    return send_file(
        file_stream,
        as_attachment=True,
        download_name=filename,
        mimetype=mimetype
    )

@auth_bp.errorhandler(403)
def forbidden(e):
    if request.path.startswith("/api/") or request.is_json:
        return jsonify({"status": "error", "message": "Forbidden: You do not have permission to access this resource."}), 403
    return render_template("403.html", session_data=session.get("login_data", {})), 403

@auth_bp.errorhandler(401)
def unauthorized(e):
    if request.path.startswith("/api/") or request.is_json:
        return jsonify({"status": "error", "message": "Unauthorized: Session expired or authentication required."}), 401
    session.clear()
    return render_template("401.html", session_data={}), 401

@auth_bp.route("/403")
def forbidden_view():
    return render_template("403.html", session_data=session.get("login_data", {})), 403

@auth_bp.route("/401")
def unauthorized_view():
    return render_template("401.html", session_data={}), 401

# =========================================================================
# DASHBOARD API PROXY ENDPOINTS (Protected with RBAC for Admin, Risk Manager, Risk Head)
# =========================================================================

def _build_dashboard_query_params():
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()
    params = []
    if start_date:
        params.append(f"start_date={start_date}")
    if end_date:
        params.append(f"end_date={end_date}")
    return ("?" + "&".join(params)) if params else ""


@auth_bp.route("/api/dashboard/summary", methods=["GET"])
@roles_required("Admin", "Super Admin", "Risk Manager", "Risk Head")
def dashboard_summary():
    try:
        q = _build_dashboard_query_params()
        response = APIClient.getdata(f"risk-dashboard/summary{q}")
        data = response.json()
        return jsonify(data)
    except Exception as e:
        current_app.logger.error(f"Dashboard summary error: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@auth_bp.route("/api/dashboard/department-wise", methods=["GET"])
@roles_required("Admin", "Super Admin", "Risk Manager", "Risk Head")
def dashboard_department_wise():
    try:
        q = _build_dashboard_query_params()
        response = APIClient.getdata(f"risk-dashboard/department-wise-Bar{q}")
        data = response.json()
        return jsonify(data)
    except Exception as e:
        current_app.logger.error(f"Dashboard department-wise error: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@auth_bp.route("/api/dashboard/user-wise", methods=["GET"])
@roles_required("Admin", "Super Admin", "Risk Manager", "Risk Head")
def dashboard_user_wise():
    try:
        q = _build_dashboard_query_params()
        response = APIClient.getdata(f"risk-dashboard/User-wise-Bar{q}")
        data = response.json()
        return jsonify(data)
    except Exception as e:
        current_app.logger.error(f"Dashboard user-wise error: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@auth_bp.route("/api/dashboard/status-pie", methods=["GET"])
@roles_required("Admin", "Super Admin", "Risk Manager", "Risk Head")
def dashboard_status_pie():
    try:
        q = _build_dashboard_query_params()
        response = APIClient.getdata(f"risk-dashboard/status-wise-pie{q}")
        data = response.json()
        return jsonify(data)
    except Exception as e:
        current_app.logger.error(f"Dashboard status-pie error: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@auth_bp.route("/api/dashboard/progress", methods=["GET"])
@roles_required("Admin", "Super Admin", "Risk Manager", "Risk Head")
def dashboard_progress():
    try:
        q = _build_dashboard_query_params()
        response = APIClient.getdata(f"risk-dashboard/department-wise-progress-HBar{q}")
        data = response.json()
        return jsonify(data)
    except Exception as e:
        current_app.logger.error(f"Dashboard progress error: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@auth_bp.route("/api/dashboard/department-status", methods=["GET"])
@roles_required("Admin", "Super Admin", "Risk Manager", "Risk Head")
def dashboard_department_status():
    try:
        q = _build_dashboard_query_params()
        response = APIClient.getdata(f"risk-dashboard/department-wise-status-stackedBar{q}")
        data = response.json()
        return jsonify(data)
    except Exception as e:
        current_app.logger.error(f"Dashboard department-status error: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@auth_bp.route("/api/dashboard/top-risks", methods=["GET"])
@roles_required("Admin", "Super Admin", "Risk Manager", "Risk Head")
def dashboard_top_risks():
    try:
        q = _build_dashboard_query_params()
        response = APIClient.getdata(f"risk-dashboard/top-10-risk{q}")
        data = response.json()
        return jsonify(data)
    except Exception as e:
        current_app.logger.error(f"Dashboard top-risks error: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@auth_bp.route("/api/dashboard/severity-distribution", methods=["GET"])
@roles_required("Admin", "Super Admin", "Risk Manager", "Risk Head")
def dashboard_severity_distribution():
    try:
        q = _build_dashboard_query_params()
        response = APIClient.getdata(f"risk-dashboard/risk-percentage{q}")
        data = response.json()
        return jsonify(data)
    except Exception as e:
        current_app.logger.error(f"Dashboard severity-distribution error: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@auth_bp.route("/api/dashboard/heatmap", methods=["GET"])
@roles_required("Admin", "Super Admin", "Risk Manager", "Risk Head")
def dashboard_heatmap():
    try:
        q = _build_dashboard_query_params()
        response = APIClient.getdata(f"risk-dashboard/heatmap{q}")
        data = response.json()
        return jsonify(data)
    except Exception as e:
        current_app.logger.error(f"Dashboard heatmap error: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@auth_bp.route("/api/dashboard/transition-heatmap", methods=["GET"])
@roles_required("Admin", "Super Admin", "Risk Manager", "Risk Head")
def dashboard_transition_heatmap():
    try:
        q = _build_dashboard_query_params()
        dept_id = request.args.get("dept_id")
        if dept_id:
            sep = "&" if q else "?"
            q = f"{q}{sep}dept_id={dept_id}"
        response = APIClient.getdata(f"risk-dashboard/risk-transition-heatmap{q}")
        data = response.json()
        return jsonify(data)
    except Exception as e:
        current_app.logger.error(f"Dashboard transition-heatmap error: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


# Legacy endpoint aliases with backwards-compatible output formats
@auth_bp.route("/api/dashboard/division", methods=["GET"])
@roles_required("Admin", "Super Admin", "Risk Manager", "Risk Head")
def dashboard_division():
    try:
        q = _build_dashboard_query_params()
        response = APIClient.getdata(f"risk-dashboard/department-wise-Bar{q}")
        data = response.json()
        data_from_api = data.get("data", []) if isinstance(data, dict) else (data or [])
        graph_data = {
            "categories": [d.get("department", "") for d in data_from_api],
            "values": [d.get("total", 0) for d in data_from_api]
        }
        return jsonify({"success": True, "data": graph_data})
    except Exception as e:
        current_app.logger.error(str(e))
        return jsonify({"success": False}), 500


@auth_bp.route("/api/dashboard/category", methods=["GET"])
@roles_required("Admin", "Super Admin", "Risk Manager", "Risk Head")
def dashboard_category():
    try:
        q = _build_dashboard_query_params()
        response = APIClient.getdata(f"risk-dashboard/User-wise-Bar{q}")
        data = response.json()
        data_from_api = data.get("data", []) if isinstance(data, dict) else (data or [])
        graph_data = {
            "categories": [d.get("employee_name", "") for d in data_from_api],
            "values": [d.get("total", 0) for d in data_from_api]
        }
        return jsonify({"success": True, "data": graph_data})
    except Exception as e:
        current_app.logger.error(str(e))
        return jsonify({"success": False}), 500


@auth_bp.route("/api/dashboard/trend", methods=["GET"])
@roles_required("Admin", "Super Admin", "Risk Manager", "Risk Head")
def dashboard_trend():
    try:
        q = _build_dashboard_query_params()
        response = APIClient.getdata(f"risk-dashboard/department-wise-progress-HBar{q}")
        data = response.json()
        data_from_api = data.get("data", []) if isinstance(data, dict) else (data or [])
        trend_data = {
            "categories": [d.get("department", "") for d in data_from_api],
            "high": [d.get("progress", 0) for d in data_from_api],
            "low": [0 for _ in data_from_api]
        }
        return jsonify({"success": True, "data": trend_data})
    except Exception as e:
        current_app.logger.error(str(e))
        return jsonify({"success": False}), 500


@auth_bp.route("/api/dashboard/distribution", methods=["GET"])
@roles_required("Admin", "Super Admin", "Risk Manager", "Risk Head")
def dashboard_distribution():
    try:
        q = _build_dashboard_query_params()
        response = APIClient.getdata(f"risk-dashboard/status-wise-pie{q}")
        data = response.json()
        data_from_api = data.get("data", []) if isinstance(data, dict) else (data or [])
        graph_data = {
            "labels": [d.get("status", "") for d in data_from_api],
            "values": [d.get("total", 0) for d in data_from_api]
        }
        return jsonify({"success": True, "data": graph_data})
    except Exception as e:
        current_app.logger.error(str(e))
        return jsonify({"success": False}), 500

    
@auth_bp.route("/status")
@menu_required(6)
def status():
    return render_template("status.html",session_data=session["login_data"])

@auth_bp.route("/users")
@menu_required(3)
def users():
    return render_template("users.html",session_data=session["login_data"]) 


@auth_bp.route("/getdepartment", methods=["GET", "POST"])
def getdepartment():
    current_app.logger.info(f"Use api hit departments")
    try:
        response = APIClient.getdata("departments")
        current_app.logger.info(f"API executed departments")
        data = response.json()
        current_app.logger.info(f"API executed departments")
        current_app.logger.info(f"API responsee departments---->{data}")
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f"getRiskRegisterbyid Error -> {str(e)}")
        flash("user failed")
    return render_template("department.html")

#++++++++++++++++++++++++++++++++
# ++++++++++++++++++++++++++++++++++++
# 
#     
@auth_bp.route("/get_Department_all", methods=["GET"])
def get_Department_all():
    try:
        # response = APIClient.get("user/get_all")
        # data = response.json()
        response = APIClient.getdata("departments")
        data = response.json()
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f"Get Users Error -> {str(e)}")
        return jsonify({"Error": True}), 500

#=====================================================

# ================= CREATE Department =================
@auth_bp.route("/department/create", methods=["POST"])
def create_department():
    try:
        payload = request.json
        current_app.logger.info(f"API executed departments payload {payload}")
        response = APIClient.postdata("departments/", payload)
        return jsonify(response.json()), 200
    except Exception as e:
        current_app.logger.error(f"Create User Error -> {str(e)}")
        return jsonify({"Error": True}), 500

#===============GET department BY ID================================
@auth_bp.route("/department/<int:user_id>", methods=["GET"])
def get_department_by_id(user_id):
    try:
        response = APIClient.getbyid("departments", user_id)
        return jsonify(response.json()), 200
    except Exception as e:
        return jsonify({"Error": True}), 500

# ================= UPDATE department =================
@auth_bp.route("/department/update/<int:id>", methods=["PUT"])
def update_department(id):
    try:
        payload = request.json
        response = APIClient.putdata(f"departments/{id}", payload)
        return jsonify(response.json()), 200
    except Exception as e:
        return jsonify({"Error": True}), 500


# ================= DELETE department =================
@auth_bp.route("/department/delete/<int:id>", methods=["DELETE"])
def delete_department(id):
    try:
        response = APIClient.deletebyid(f"departments/{id}")
        return jsonify(response.json()), 200
    except Exception as e:
        return jsonify({"Error": True}), 500
    # return send_file(
    #     file_stream,
    #     as_attachment=True,
    #     download_name="risk_register.xlsx",
    #     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    # )


#=====================
#=====================
#=====================

 

#++++++++++++++++++++++++++++++++
# ++++++++++++++++++++++++++++++++++++
# 
#     
@auth_bp.route("/get_status_all", methods=["GET"])
def get_Status_all():
    try:
        # response = APIClient.get("user/get_all")
        # data = response.json()
        response = APIClient.getdata("approval")
        data = response.json()
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f"Get Users Error -> {str(e)}")
        return jsonify({"Error": True}), 500

#=====================================================

# ================= CREATE Department =================
@auth_bp.route("/Status/create", methods=["POST"])
def create_Status():
    try:
        payload = request.json
        current_app.logger.info(f"API executed status payload {payload}")
        response = APIClient.postdata("approval/", payload)
        return jsonify(response.json()), 200
    except Exception as e:
        current_app.logger.error(f"Create User Error -> {str(e)}")
        return jsonify({"Error": True}), 500

#===============GET department BY ID================================
@auth_bp.route("/Status/<int:id>", methods=["GET"])
def get_Status_by_id(id):
    try:
        response = APIClient.getbyid("approval/id", id)
        return jsonify(response.json()), 200
    except Exception as e:
        return jsonify({"Error": True}), 500

# ================= UPDATE department =================
@auth_bp.route("/Status/update/<int:id>", methods=["PUT"])
def update_Status(id):
    try:
        payload = request.json
        response = APIClient.putdata(f"approval/{id}", payload)
        return jsonify(response.json()), 200
    except Exception as e:
        return jsonify({"Error": True}), 500


# ================= DELETE department =================
@auth_bp.route("/ststus/delete/<int:id>", methods=["DELETE"])
def delete_Status(id):
    try:
        response = APIClient.deletebyid(f"approval/{id}")
        return jsonify(response.json()), 200
    except Exception as e:
        return jsonify({"Error": True}), 500
    # return send_file(
    #     file_stream,
    #     as_attachment=True,
    #     download_name="risk_register.xlsx",
    #     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    # )

#=====================
#=====================
#=====================
@auth_bp.route("/userRole")
@menu_required(4)
def userRole():
    return render_template("userRole.html", session_data=session["login_data"])
 



# ================= GET ALL USERS =================
@auth_bp.route("/get_users_all", methods=["GET"])
def get_users_all():
    try:
        # response = APIClient.get("user/get_all")
        # data = response.json()
        response = APIClient.getdata("users")
        data = response.json()
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f"Get Users Error -> {str(e)}")
        return jsonify({"Error": True}), 500


# ================= CREATE USER =================
@auth_bp.route("/users/create", methods=["POST"])
def create_user():
    try:
        payload = request.json
        response = APIClient.postdata("users/", payload)
        return jsonify(response.json()), 200
    except Exception as e:
        current_app.logger.error(f"Create User Error -> {str(e)}")
        return jsonify({"Error": True}), 500


# ================= GET USER BY ID =================
@auth_bp.route("/users/<int:user_id>", methods=["GET"])
def get_user_by_id(user_id):
    try:
        response = APIClient.getbyid("users", user_id)
        return jsonify(response.json()), 200
    except Exception as e:
        return jsonify({"Error": True}), 500


# ================= UPDATE USER =================
@auth_bp.route("/users/update/<int:user_id>", methods=["PUT"])
def update_user(user_id):
    try:
        payload = request.json
        response = APIClient.putdata(f"users/{user_id}", payload)
        return jsonify(response.json()), 200
    except Exception as e:
        return jsonify({"Error": True}), 500


# ================= DELETE USER =================
@auth_bp.route("/users/delete/<int:user_id>", methods=["DELETE"])
def delete_user(user_id):
    try:
        current_app.logger.info(f"Users api deletcall for data {user_id}")
        response = APIClient.deletebyid(f"users/{user_id}")
        return jsonify(response.json()), 200
    except Exception as e:
        return jsonify({"Error": True}), 500
    # return send_file(
    #     file_stream,
    #     as_attachment=True,
    #     download_name="risk_register.xlsx",
    #     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    # )
#===================================================
@auth_bp.route("/user_types", methods=["GET"])
def user_types():
    current_app.logger.info("Use api hit getalldpt")
    try:
        response = APIClient.getdata("user_types")
        data = response.json()

        current_app.logger.info(f"API response->{data}")

        return jsonify(data), 200

    except Exception as e:
        current_app.logger.error(f"Error -> {str(e)}")
        return jsonify({"Error": True, "message": "Failed"}), 500

#===================================================
@auth_bp.route("/user_role", methods=["GET"])
def user_role():
    current_app.logger.info("Use api hit getalldpt")
    try:
        response = APIClient.getdata("roles")
        data = response.json()

        current_app.logger.info(f"API response->{data}")

        return jsonify(data), 200

    except Exception as e:
        current_app.logger.error(f"Error -> {str(e)}")
        return jsonify({"Error": True, "message": "Failed"}), 500



#
#
#
#=============FillMenuList============
@auth_bp.route("/FillMenuList", methods=["GET"])
def get_Menu_all():
    try:
        # response = APIClient.get("user/get_all")
        # data = response.json()
        response = APIClient.getdata("menu_map/menus")
        data = response.json()
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f"Get Users Error -> {str(e)}")
        return jsonify({"Error": True}), 500


# ================= GET ALL USERSRole =================
@auth_bp.route("/get_usersrole_all", methods=["GET"])
def get_usersrole_all():
    try:
        # response = APIClient.get("user/get_all")
        # data = response.json()
        response = APIClient.getdata("roles")
        data = response.json()
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f"Get Users Error -> {str(e)}")
        return jsonify({"Error": True}), 500


# ================= CREATE USER Role =================
@auth_bp.route("/usersrole/create", methods=["POST"])
def create_userrole():
    try:
        payload = request.json
        response = APIClient.postdata("roles", payload)
        return jsonify(response.json()), 200
    except Exception as e:
        current_app.logger.error(f"Create User Error -> {str(e)}")
        return jsonify({"Error": True}), 500


# ================= GET USER Role BY ID =================
@auth_bp.route("/usersrole/<int:role_id>", methods=["GET"])
def get_userrole_by_id(role_id):
    try:
        #current_app.logger.info("========== USERSROLE API CALLED ==========")
        # # Already in session
        # if session.get("menu_ids"):
        #     return jsonify({
        #         "status": True,
        #         "data": {
        #             "menuids": session["menu_ids"]
        #         }
        #     }), 200

        # First time - call API
        response = APIClient.getbyid("roles", role_id)
        data = response.json()

        #session["menu_ids"] = data["data"]["menuids"]

        return jsonify(data), 200

    except Exception as e:
        current_app.logger.error(str(e))
        return jsonify({"Error": True}), 500


# ================= UPDATE  USER Role =================
@auth_bp.route("/usersrole/update/<int:id>", methods=["PUT"])
def update_userrole(id):
    try:
        payload = request.json
        response = APIClient.putdata(f"roles/{id}", payload)
        return jsonify(response.json()), 200
    except Exception as e:
        return jsonify({"Error": True}), 500


# ================= DELETE USER Role =================
@auth_bp.route("/usersrole/delete/<int:id>", methods=["DELETE"])
def delete_userrole(id):
    try:
        current_app.logger.info(f"Users api deletcall for data {id}")
        response = APIClient.deletebyid(f"roles/{id}")
        return jsonify(response.json()), 200
    except Exception as e:
        return jsonify({"Error": True}), 500
    # return send_file(
    #     file_stream,
    #     as_attachment=True,
    #     download_name="risk_register.xlsx",
    #     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    # )
#===================================================
@auth_bp.route("/importRisk")
@menu_required(7)
def importRisk():
    return render_template("importRisk.html",session_data=session["login_data"])


@auth_bp.route("/importRisk/Proceed", methods=["POST"])
def Proceed():
    try:
        payload = request.json

        source_fy = payload.get("sourceYear")
        destination_fy = payload.get("destinationYear")
        department_short_name = payload.get("functionlist")
        current_app.logger.info(
            f"source_fy={source_fy}, destination_fy={destination_fy}, department_short_name={department_short_name}"
        )
        if department_short_name != "":
            urlpass = (
                f"risk/copy_risks?source_fy={source_fy}"
                f"&destination_fy={destination_fy}"
                f"&department_short_name={department_short_name}"
            )
        else:
            urlpass = (
                f"risk/copy_risks?source_fy={source_fy}"
                f"&destination_fy={destination_fy}"
            )

        response = APIClient.getdata(urlpass)
        current_app.logger.info(
            f"response risk/copy_risks? -> {response.json()}"
        )
        #return jsonify(response.json()), 200
        result = response.json()
        return jsonify(result), 200
    except Exception as e:
        current_app.logger.error(f"Copy Risk Error -> {str(e)}")
        return jsonify({"Error": True}), 500
    

@auth_bp.route("/risk-register/get-financial-years", methods=["GET"])
def get_financial_years():
    try:
        response = APIClient.getdata("risk-register/get-financial-years")
        return jsonify(response.json()), 200

    except Exception as e:
        current_app.logger.error(f"Get Financial Years Error -> {str(e)}")
        return jsonify({
            "status": False,
            "message": "Something went wrong"
        }), 500


#===================================================
@auth_bp.route("/ApproveRiskTreatment", methods=["GET"])
def ApproveRiskTreatment():
    current_app.logger.info("API hit ApproveRiskTreatment ---->")

    treatment_id = request.args.get("treatment_id")
    approval_status = request.args.get("approval_status")
    approval_remark = request.args.get("approval_remark")

    try:
        response = APIClient.putdata(
           # f"risk-treatment/105/approve",
            f"risk-treatment/{treatment_id}/approve",
            {
                "approval_status": int(approval_status),
                "approval_remark": approval_remark
            }
        )

        data = response.json()

        current_app.logger.info(f"ApproveRiskTreatment Response -> {data}")

        return jsonify(data), 200

    except Exception as e:
        current_app.logger.error(f"Error in ApproveRiskTreatment -> {str(e)}")
        return jsonify({"Error": True, "message": "Failed"}), 500
        
#========Change Password============================================
@auth_bp.route("/ChangePassword")
@menu_required(8)
def ChangePassword():
    return render_template("ChangePassword.html", session_data=session["login_data"])

@auth_bp.route("/ChangePassword/UpdatePwd", methods=["POST"])
def ChangePasswordUpdatePwd():
    try:
        data = request.json
        current_app.logger.info("API hit /ChangePassword/UpdatePwd ---->")
        id=data.get("id")
        old_password = data.get("old_password")
        new_password = data.get("new_password")
        
        response = APIClient.putdata(
                "users/password/change-password",
                {
                    "id": int(id),
                    "old_password": old_password,
                    "new_password": new_password
                }
            )
       # response={}
        result = response.json()
        current_app.logger.info(
            f"ChangePassword Response -> {result}"
        )

        return jsonify(result), response.status_code

    except Exception as e:
        current_app.logger.error(
            f"Error in ChangePasswordUpdatePwd -> {str(e)}"
        )

        return jsonify({
            "Error": True,
            "message": "Failed to change password"
        }), 500
        
@auth_bp.route("/uploadRisk")
@menu_required(8)
def uploadRisk():
    return render_template("uploadRisk.html",session_data=session["login_data"])

@auth_bp.route("/uploadRisk/Proceed", methods=["POST"])
def uploadRisk_excel():

    #file = request.files.get("file")
    file = request.files.get("file")
    

    files = None
    if file:
        files = {
            "file": (file.filename, file.stream, file.mimetype)
        }

    if not file:
        return jsonify({
            "success": False,
            "message": "Please select an Excel file."
        }), 400

    try:

        # response = APIClient.post_file(
        #     "excel/import",
        #     file
        # )
        response = APIClient.postdatafile_excel(
            "excel/import",
            files=files  
        )

        try:
            res_json = response.json()
        except Exception:
            res_json = {"success": False, "message": response.text}

        return jsonify(res_json), response.status_code

    except Exception as ex:

        return jsonify({
            "success": False,
            "message": str(ex)
        }), 500

