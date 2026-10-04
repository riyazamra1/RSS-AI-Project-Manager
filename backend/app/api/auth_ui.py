from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["auth-ui"])

# Public, non-sensitive configuration consumed by the native RSS AI Project Manager
# client. Authentication endpoints, API destinations, and security policy remain
# native/server-controlled and are never supplied by this document.
AUTH_UI_CONFIG = {
    "version": 1,
    "kit_version": "1.0.0",
    "logo_url": "https://raw.githubusercontent.com/riyazamra1/RSS-AI-Project-Manager/main/web/assets/rss-ai-project-manager-logo.png",
    "title": "Welcome to RSS AI Project Manager",
    "subtitle": "Secure access to your RSS workspace.",
    "sign_in_label": "Sign In",
    "create_account_label": "Create Account",
    "login_button_label": "Sign in",
    "register_button_label": "Request account",
    "registration_title": "Create your RSS account",
    "registration_subtitle": "Submit your account request. Verify your email and wait for administrator approval.",
    "policy_label": "I agree to the Terms of Service and Privacy Policy",
    "policy_required_message": "Please accept the Terms of Service and Privacy Policy to continue.",
    "submitting_label": "Submitting request…",
    "signing_in_label": "Signing in…",
}


@router.get("/ui-config")
def auth_ui_config():
    return AUTH_UI_CONFIG
