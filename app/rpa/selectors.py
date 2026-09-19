"""Central selector map for the CPGRAMS portal (pgportal.gov.in).

WARNING: CPGRAMS changes its DOM without notice. These selectors MUST be
verified against the live portal before use, and re-checked periodically.
Prefer role/text-based selectors (more robust than brittle CSS).

Each entry documents what it targets; keep the live-DOM confirmation note
(`# TODO VERIFY against live portal`) until you've watched it work once.
"""

SELECTORS = {
    # --- Login (VERIFIED against live portal, 2026-08) ---
    # The login view is served directly at /Signin (homepage link href=/Signin).
    # Single POST; the browser client-side double-hashes the password on submit
    # (sha512(sha256(pw) + static salt)), which runs automatically when we
    # click #btnSubmit. An ALTERNATE "Login with OTP" route exists at
    # /Signin/Login (same form, OTP entered into TempPassword) -- used by the
    # citizen themselves, not by our automation.
    "signin_url": "https://pgportal.gov.in/Signin",
    "login_link": "a:has-text('Login')",
    "login_username": "input#Username",
    "login_password": "input#TempPassword",  # actual password field on Signin
    "login_submit": "button#btnSubmit",  # text 'Login', type=submit
    # Captcha image is served at /Captcha/GetCaptcha with id=CaptchaImage.
    "captcha": "img#CaptchaImage",
    "captcha_input": "input#Captcha",
    # Post-login OTP/second-factor: NOT statically present on /Signin. Whether
    # a session survives from a plain password login is the open empirical
    # question to confirm with a real account.
    "otp_input": "input[name*='otp' i], input[id*='otp' i], input[placeholder*='otp' i]",  # TODO VERIFY: only if portal demands OTP after login
    "otp_submit": "button:has-text('Verify'), button:has-text('Submit'), input[type='submit']",  # TODO VERIFY

    # --- Grievance form entry ---
    # Auth-aware pages: /Desk (200 "Welcome : <name>" when authed, 403 ->
    # /Error/Unauthorized when not). /Home/LodgeGrievance is the ANONYMOUS entry
    # point: it shows a "Login First" gate, but once logged in the same route
    # returns 403 and wipes the session cookies (never navigate there while
    # authenticated; the logged-in filing path goes via /Desk).
    "desk_url": "https://pgportal.gov.in/Desk",
    "welcome_text": "text=/Welcome\\s*:/i",
    "not_authorized_text": "text=/You are not authorized to access this resource/i",
    "lodge_grievance_url": "https://pgportal.gov.in/Home/LodgeGrievance",  # anonymous entry only
    "lodge_grievance": "a:has-text('Lodge Public Grievance')",
    "logged_in_link": "a:has-text('Logout'), a:has-text('Log Out'), a:has-text('My Dashboard')",
    "login_required_text": "text=/Grievance can now be lodged only by registered users/i",
    "agree_terms": "button:has-text('Submit'), label:has-text('I agree')",

    # --- Department selection (VERIFIED: V7 guided questionnaire) ---
    # Flow (all on pgportal.gov.in, requires the linked session):
    #  /NewGrievance  -> terms: check #termscondition, click #submit
    #  /NewGrievance/Organisation -> pick #moreOrg
    #  /V7/NewGrievance/Index/<token> -> level-by-level #Category_2..#Category_N,
    #        then #Remarks, then #btnNext
    #  /V7/NewGrievance/Details -> #GrievanceDescription.. then FINAL #Captcha,
    #        then #submit
    "new_grievance_url": "https://pgportal.gov.in/NewGrievance",
    "terms_checkbox": "input#termscondition",
    "terms_submit": "button#submit",
    "org_select": "select#moreOrg",
    "category_level_selects": "select[name='Category']",
    "remarks_textarea": "textarea#Remarks",
    "btn_next": "button#btnNext",
    "description_textarea": "textarea#GrievanceDescription",
    "name_input": "input#Name",
    "gender_radio": "input[name='Gender']",
    "country_select": "select#Country",
    "state_select": "select#State",
    "district_select": "select#District",
    "address1_input": "input#Address1",
    "address2_input": "input#Address2",
    "address3_input": "input#Address3",
    "pincode_input": "input#Pincode",
    "email_input": "input#EmailId",
    "mobile_input": "input#MobileNo",
    "final_captcha_input": "input#Captcha",
    "submit_button": "button#submit",

    # --- Confirmation / registration ID ---
    # Registration id formats: "CPGRAMS-XXXXXXXXXXXXXX" or 16-digit numbers.
    "confirmation_page": "text=/Registration (?:Id|Number|No)/i, text=/Grievance (?:Id|Number)/i",

    # --- Citizen profile (authenticated /EditProfile) ---
    # The citizen's own account page. Auth-gated; shows the details captured at
    # registration (name, gender, address, state, district, pincode, mobile,
    # email). Field names mirror the /Registration form; re-verify against the
    # live page if the portal is redesigned.
    "edit_profile_url": "https://pgportal.gov.in/EditProfile",
    "profile_name_input": "input#Name",
    "profile_email_input": "input#EmailAddress, input#EmailId",
    "profile_mobile_input": "input#MobileNo",
    "profile_phone_input": "input#PhoneNo",
    "profile_gender_radio": "input[name='Sex'], input[name='Gender']",
    "profile_address_inputs": "input#Address1, input#Address2, input#Address3",
    "profile_state_select": "select#State",
    "profile_district_select": "select#District",
    "profile_pincode_input": "input#Pincode",
    "profile_country_select": "select#Country",
}
