# RSS AI Project Manager — Central 13-Project Registry Checklist

This is the canonical registry checklist for the RSS portfolio. It keeps the 13 tracked projects visible in one place and is intentionally separate from the runtime project configuration.

## Registry rules

- [ ] Every tracked RSS project has a unique project ID.
- [ ] Every project has its canonical display name.
- [ ] Every project has its GitHub repository mapping.
- [ ] Every project has an enabled/disabled state.
- [ ] Every project has a priority.
- [ ] Every project has a current development status.
- [ ] Every project has a current release-readiness status.
- [ ] Every project can be linked to permanent project memory.
- [ ] New RSS repositories can be added without changing the architecture.
- [ ] RSS Autopilot is tracked as the central controller and is not counted as a product slot beyond the 13-project portfolio.

## 13-project master checklist

| # | Project | Project ID | GitHub repository | Registry |
|---:|---|---|---|:---:|
| 1 | RSS CLOUD SYNC | `rss-cloud-sync` | `riyazamra1/RSS-Cloud-Sync` | [ ] |
| 2 | RSS MONEY MANAGER | `rss-money-manager` | `riyazamra1/RSS-Money-Manager` | [ ] |
| 3 | RSS PASSWORD MANAGER | `rss-password-manager` | `riyazamra1/RSS-Password-Manager` | [ ] |
| 4 | RSS AI ASSISTANT | `rss-ai-assistant` | `riyazamra1/RSS-Ai-Assistant` | [ ] |
| 5 | RSS CLIPBOARD | `rss-clipboard` | `riyazamra1/RSS-Clipboard` | [ ] |
| 6 | RSS LAUNCHER | `rss-launcher` | `riyazamra1/RSS-Launcher` | [ ] |
| 7 | RSS RDP CLOUD PC | `rss-rdp-cloud-pc` | `riyazamra1/RSS-RDP-Cloud-PC` | [ ] |
| 8 | RSS DEVICE GUARDIAN | `rss-device-guardian` | `riyazamra1/RSS-Device-Guardian` | [ ] |
| 9 | RSS AUTOPILOT | `rss-autopilot` | `riyazamra1/RSS-Autopilot` | [ ] |
| 10 | RSS CALLER ID | `rss-caller-id` | `riyazamra1/RSS-Caller-ID` | [ ] |
| 11 | RSS WHATSAPP AUTOMATION | `rss-whatsapp-automation` | `riyazamra1/RSS-Whatsapp-Automation` | [ ] |
| 12 | RSS MOBILE RELOAD SYSTEM | `rss-mobile-reload-system` | `riyazamra1/RSS-Mobile-Reload-System` | [ ] |
| 13 | RAZEEN SECURE SOLUTION WEBSITE | `razeen-secure-solution-website` | `riyazamra1/Razeen_Secure_Solution_Website` | [ ] |

## Required status fields

For each project, the central manager should maintain:

- [ ] Latest work
- [ ] Completed items
- [ ] Current status
- [ ] Remaining work
- [ ] Next step
- [ ] Development percentage
- [ ] Release percentage/readiness
- [ ] Latest activity timestamp
- [ ] Permanent memory snapshot
- [ ] Repository synchronization state

## Controller

**RSS AUTOPILOT** is the central automation/controller project. It coordinates project automation but must remain separately identifiable from the product projects.

## Acceptance gate

The registry is considered complete only when all 13 rows are represented in the central project database, each has a valid repository mapping, and each can be loaded by the project-status API.
