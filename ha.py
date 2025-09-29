cs_id = item.get("CodingStandardId")
cs_object = self.cs_quick_access_map.get(cs_id, {})

# Get severity safely
severity = cs_object.get("severity", "Information")
severity_icon = "❌" if severity.lower() == "error" else "⚠️" if severity.lower() == "warning" else "ℹ️"

# Fix key mismatch for confidence score
confidence_score = (
    item.get("ConfidenceScore") or
    item.get("ConfidentScore") or
    "N/A"
)

# Business mapping
if severity.lower() == "information":
    severity = "JAS"

combined_body = (
    f"**Severity:** {severity_icon} {severity}  |  "
    f"**Confidence_Score:** {confidence_score}\n\n"
)
