# Google OAuth publication and verification

Prepared against official Google documentation checked on **October 30, 2026**. Console labels and requirements can change; follow the linked official guidance and the status shown for your actual project.

**Current Cloud status has not been independently checked.** The developer confirmed on October 31, 2026 that the API works and testing is complete; the requested next step is website publication. External / Testing was reported in the original preparation brief and is not assumed to be the current live Console state. No repository change, Windows build, website deployment, or GitHub Release changes Google's publishing or verification status. This guide remains a reference for any Console steps still applicable; it does not claim that Unified Scheduler is approved.

## Who completes each part

| Responsibility | What it covers |
| --- | --- |
| Repository implementation | Desktop browser authorization, PKCE and loopback callback, app-owned client configuration, secure user-token storage, refresh/reconnect handling, release packaging, website source and tests. |
| Application owner | Actual Cloud project/client, support and privacy contacts, website/domain, Console configuration, demonstration video, verification submission, release decisions and live account tests. |
| Google | Brand and scope reviews, approval or rejection, warnings, enforcement and OAuth quotas. Workspace administrators can independently restrict organization accounts. |

The desktop application remains useful for local tasks, reminders and Moodle subscriptions without Google authorization. Users of a configured build need only select **Connect Google Account** and complete Google's browser consent; they do not create Cloud projects or supply configuration files.

## Testing, publishing and approval are different states

| External app state | Who can authorize Calendar access? | Expected experience |
| --- | --- | --- |
| Testing | Explicitly registered test accounts, up to 100 testers. | Testing warning; authorization and refresh token normally expire seven days after consent. |
| In Production, verification incomplete | The Testing allowlist no longer applies, subject to Google's account/policy restrictions. | Sensitive-scope requests can show an unverified-app warning and face the separate unverified-user cap. This is not the final public-release target. |
| In Production, brand and requested scopes approved | Eligible Google accounts, subject to account and organization policies. | Approved branding and consent scopes; the unverified warning/cap does not apply to the approved scope set. Normal token expiration/revocation still applies. |

See Google's [app-state comparison](https://developers.google.com/identity/protocols/oauth2/production-readiness/overview). Publishing is a developer action; verification is a Google decision.

The **100 test-user limit** and **100 new-user lifetime cap for unverified sensitive/restricted access** are different limits. Removing a tester or recreating local credentials does not reset the project's unverified-user cap. Google's identity-only exception does not apply here because Unified Scheduler requests Calendar access. The Console's Audience page is the authority for the selected project's status and limits. [Manage App Audience](https://support.google.com/cloud/answer/15549945)

Production authorization is not permanent authorization. Refresh can fail after user revocation, six months without use, excessive live tokens, expiry of time-limited consent, or administrator restrictions. Google currently documents a limit of 100 refresh tokens per Google account per OAuth client, with older tokens invalidated when exceeded. The special seven-day Testing rule does not apply to newly issued production authorizations; do not assume publishing extends previously issued Testing tokens. Reauthorize after the transition. [Refresh-token expiration](https://developers.google.com/identity/protocols/oauth2#expiration)

## Scope inventory and justification

The code's `SCOPES` in [`providers/google.py`](../src/unified_scheduler/providers/google.py) is the release authority. Declare exactly these scopes in the production project's **Data Access** page:

| Scope | Unified Scheduler use |
| --- | --- |
| `openid` | Verify the signed Google identity, including stable subject and nonce, before associating a connected account. |
| `https://www.googleapis.com/auth/userinfo.email` | Show the verified email so users can distinguish multiple Google accounts. |
| `https://www.googleapis.com/auth/calendar.calendarlist.readonly` | List subscribed calendars and let users choose which calendars appear locally. |
| `https://www.googleapis.com/auth/calendar.events.readonly` | Read events from selected calendars into the schedule, local cache and reminders. |

The two Calendar scopes match [`calendarList.list`](https://developers.google.com/workspace/calendar/api/v3/reference/calendarList/list) and [`events.list`](https://developers.google.com/workspace/calendar/api/v3/reference/events/list). The application does not write Google events, alter subscriptions, inspect sharing ACLs, or change Google settings. Free/busy-only access cannot supply event titles, descriptions, locations and deadlines. Owned-events-only access would exclude shared calendars that the app supports. The older broad `calendar.readonly` scope is no longer requested for new connections. Review existing grants during the migration below. See the [Calendar scope reference](https://developers.google.com/workspace/calendar/api/auth).

Google identifies reading Calendar events as a sensitive use. Check each scope's current classification in **Data Access** and prepare the review it requires; read-only does not mean verification-free. Do not infer the classification of one granular scope from another or promise that no review is necessary. [Sensitive-scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification)

Suggested app-specific scope justification for the submission:

> Unified Scheduler is a Windows desktop planner. The user explicitly connects a Google account to see their schedule alongside local tasks and Moodle deadlines. Calendar-list access identifies their subscribed calendars; event-read access supplies the events for the calendars they choose. The app stores a local cache for offline viewing and reminders. It makes no Calendar write requests and sends no calendar data to a developer-operated backend. Identity scopes distinguish independently connected accounts and prevent reconnecting an account as a different person.

Review that text against the final release before submitting it. Describing intended features that the reviewed executable does not implement will not establish compliance.

## Ordered owner procedure

### 1. Confirm the production project and owner access

Open [Google Cloud Console](https://console.cloud.google.com/), select the intended project and record its project ID privately. Inspect **Google Auth platform → Clients** and confirm the Desktop client used by the release belongs to that project. A similar app name is not sufficient evidence. Confirm the support team can receive email for the project's owner/editor accounts.

Keep ongoing development/testing in a separate project from the production project. If you promote the existing project, move future experimental work into a separate testing project. Changing projects or client IDs requires fresh user authorization; existing tokens cannot be transferred between client IDs. Google's [OAuth policies](https://developers.google.com/identity/protocols/oauth2/policies) require appropriate clients, maintained contacts and separate deployment-tier projects.

### 2. Enable Calendar API

In the selected project, open **APIs & Services → Library**, find **Google Calendar API**, and enable it. This is the application owner's setup, not an end-user task. Google's [Calendar setup instructions](https://developers.google.com/workspace/calendar/api/quickstart/python) cover API enablement and Desktop client creation; the quickstart's testing example is not a substitute for production verification.

### 3. Configure the consent screen and External audience

Open **Google Auth platform → Branding**. If the platform is unconfigured, use **Get Started** and enter the real app name, reachable user-support address and developer contact email. Choose **External** for users outside one Workspace organization. Review the policy acknowledgment before accepting it. Existing projects expose these settings through **Branding**, **Audience** and **Data Access**. While testing, keep only approved test accounts on the list. [Configure OAuth consent](https://developers.google.com/workspace/guides/configure-oauth-consent)

### 4. Finish and deploy the public website

Review `docs/public-site/index.html`, `privacy.html` and `terms.html`. Replace any owner/contact/domain placeholders with verified information. The contact information must be usable; a public issue tracker is not a place for users to post private calendars or credentials. Publish the static site using [the repository's website guide](PUBLIC_SITE.md).

Use the **actual public HTTPS URLs** in the following steps. Do not enter local file paths, unpublished preview URLs, a GitHub source-file URL, or example domains. The homepage must describe the desktop application and link to its privacy and terms pages. Confirm those pages load without signing in. Review the privacy text against the packaged executable and any distribution/website services you add.

### 5. Establish domain ownership

A GitHub repository or a working `github.io` page does not by itself prove that Google's OAuth domain-verification requirement is satisfied. Google asks for ownership of the registrable domain associated with the branding URLs and verification through Search Console by an account associated with the Cloud project. [Brand-verification domain requirements](https://developers.google.com/identity/protocols/oauth2/production-readiness/brand-verification#authorized-domains)

The straightforward route is a domain you control: attach it to GitHub Pages, configure its DNS and HTTPS, then add a **Domain property** in [Search Console](https://search.google.com/search-console). Publish the DNS verification record that Google supplies and keep it in place. A verified property must correspond to the actual domain you submit; GitHub's own domain verification and Google Search Console verification are separate processes. [Search Console ownership verification](https://support.google.com/webmasters/answer/9008080?hl=en)

If using a hosting-provider subdomain, establish that Google accepts and can verify the relevant domain for your project before relying on it. Do not claim ownership of `github.io` or assume site publication is approval.

### 6. Complete Branding URLs and authorized domains

Enter **Unified Scheduler**, the appropriate app logo, the owner-supplied support/privacy contact **cuizon.morell@gmail.com**, the public homepage, privacy-policy URL and terms URL. Confirm that address is reachable and selectable for this project. Add the relevant verified registrable domain under **Authorized domains**. Keep homepage and privacy policy on the same domain. Review the [brand-verification requirements](https://developers.google.com/identity/protocols/oauth2/production-readiness/brand-verification).

The website's domain is for branding and policy pages. The Windows application's OAuth callback remains its local loopback redirect; do not change it to a GitHub Pages URL or create a Web client to solve a branding requirement.

### 7. Declare scopes and check the reviewed feature set

In **Data Access → Add or remove scopes**, add the exact four scopes in the inventory above and save. Check the resulting categories. Remove unused declarations only after reconciling supported builds and any verification already granted. The request made by the executable, the declarations and the verification submission must agree. New unapproved sensitive scopes can reintroduce warnings even for a previously approved app. [Manage App Data Access](https://support.google.com/cloud/answer/15549135?hl=en)

### 8. Create or select the Desktop client and prepare the candidate

Under **Clients**, select or create an OAuth client of type **Desktop app**. Download the configuration and place it at `local-config/google-oauth-client.json`, or use the documented build override. Keep it out of source control. Build with the instructions in [README](../README.md#build-a-windows-executable) and [release documentation](RELEASE.md).

Only the validated Desktop client identity belongs in the package. Access/refresh tokens, personal databases, private Moodle URLs and service-account keys do not. A desktop client is public: its bundled client secret cannot provide server-style confidentiality. Browser consent, PKCE and identity verification protect the user authorization. See Google's [desktop OAuth flow](https://developers.google.com/identity/protocols/oauth2/native-app).

### 9. Record the demonstration video

Use the real candidate build, an authorized demonstration account and harmless sample events. Record the same app identity and client being submitted. Show **Connect Google Account**, the complete English-language Google consent screen, approval, return to the desktop app, calendar selection, displayed events and reminders. Explain how each requested permission supports the visible feature. Demonstrate a second independent account and disconnection to make the app's behavior clear.

Include the client ID where requested by Google's review instructions, but do not reveal passwords, callback codes, token files, private Moodle URLs or unrelated calendar content. Supply an accessible unlisted YouTube video; cover every production OAuth client in the project. Google's [demonstration requirements](https://support.google.com/cloud/answer/13464321?hl=en) and [Data Access guidance](https://support.google.com/cloud/answer/15549135?hl=en) define the required evidence.

### 10. Publish the intended production audience

After the candidate, website and required information are ready, review **Audience → Publishing status**. Use **Publish app** when ready to transition the intended project from Testing to **In Production**. Record the resulting Console status. This removes the Testing audience restriction; it does not approve the brand or scopes. Keep broad distribution on hold until the verification target below is satisfied. [Audience publishing status](https://support.google.com/cloud/answer/15549945)

### 11. Complete brand publication

Under **Branding**, use **Verify Branding**, resolve reported issues, then **Publish branding**. Changes remain draft until published; edits are unavailable during active review. Follow live Console labels and confirm the published status. Editing local app metadata cannot change it. [Submit for brand verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/brand-verification)

### 12. Submit the applicable scope verification

With branding published, open **Verification Center**, review the Data access status, provide scope justifications, the video, requested feature documentation and all other information Google asks for. Submit the relevant verification request and respond to follow-up email. Public Calendar event reading needs the applicable sensitive-scope review; do not choose an unrelated personal/internal exception to avoid it. Google's decision and any additional requirements determine completion. [Sensitive-scope submission](https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification)

### 13. Confirm approval for the exact release

Record the approved brand and scope set in your release records. Confirm that the release's client belongs to the approved project and that its requested scopes match the approved set. A pending request, a published audience, or successful login by a tester does not prove approval. Do not advertise verified production access until Google confirms it. Scope mismatches can cause an approved project to show warnings again. [Verification FAQ](https://support.google.com/cloud/answer/13463817?hl=en)

### 14. Reauthorize existing accounts after transition

Preserve the existing workspace. In **Accounts**, use **Reconnect Google Account** for each previously connected Google identity, approve the requested permissions, then confirm a successful sync. Reconnect should preserve local tasks, Moodle subscriptions, account identity and cached events while replacing that account's credentials. Avoid repeated reconnects merely to test expiry: additional tokens can invalidate older installations.

If an old authorization retained broader Calendar access, revoke the app's grant in the Google account's [third-party connections](https://myaccount.google.com/connections) and reconnect with the new scope set. Revocation can affect other installations using that Google account and OAuth application; coordinate this with the user. A transition to a different client/project also needs new consent. Do not assume that an existing Testing token becomes long-lived, or that narrower code automatically removes a previously granted broader scope.

### 15. Validate a fresh user and the distributed executable

Use a Google account that has **never been added to the project's test-user list**. On a clean Windows profile or test machine, extract the entire candidate folder, launch it without Python, and connect from inside the app. Confirm no JSON selector, no unexpected unverified-app warning after approval, the correct app identity, Calendar permission text and successful calendar retrieval. Also test a Workspace account when supported; its administrator can still restrict the app even after Google approval.

Connect two accounts, refresh, restart, reconnect one and remove one; confirm the other remains connected. Check a connection more than seven days after new production consent, while recognizing that normal revocation still applies. Revoke one grant remotely, confirm a clear reconnect state and retained cache, and recover by reconnecting. Run the rest of the [manual verification checklist](manual-verification.md) before approving a GitHub Release. These tests have to use the real project; mocked tests cannot establish production access.

## Google Cloud actions the owner must perform manually

- [ ] Identify the correct production project and maintain owner/editor contacts.
- [ ] Enable Calendar API; select External audience and confirm the actual current publishing status.
- [ ] Supply the real support/privacy contacts, homepage, privacy policy and terms URLs.
- [ ] Verify the website's relevant domain with Search Console and add authorized domains.
- [ ] Declare the exact scope inventory and review the current sensitivity categories.
- [ ] Select the production Desktop client and supply its configuration to the release build.
- [ ] Record the candidate's consent and Calendar feature demonstration.
- [ ] Publish the intended audience; independently verify and publish Branding.
- [ ] Submit the applicable data-access review, respond to questions and obtain Google's decision.
- [ ] Reauthorize old accounts and test a new off-list account using the candidate executable.
- [ ] Record evidence, approve release publication and keep contact/domain/scope configuration maintained.

## Diagnose access problems without bypassing restrictions

| Symptom | Owner check |
| --- | --- |
| `403: access_denied` for a new account | Confirm the client/project and live Audience status. Check the Testing allowlist if still Testing, then Workspace/Google account restrictions and review status. This error alone does not prove Testing. |
| Authorization fails again around seven days | Check whether the grant was issued during Testing. Complete the transition and obtain new consent; do not change token timestamps. |
| Unverified warning in Production | Inspect Verification Center, approved scopes and the executable's scope set. Publishing alone is insufficient. |
| App's requested scopes differ from approval | Reconcile code, Data Access and the submitted candidate; seek review before public distribution with new sensitive scopes. |
| One account requests reconnect | Check revocation/token expiry and reconnect that identity. Local tasks and other accounts should remain intact. |
| Google sign-in is not configured | The build lacks a valid Desktop client. Supply the owner configuration and rebuild; users should never create their own project. |

Warnings and restrictions are controlled by Google, including possible later policy changes. Do not rotate projects, imitate an approved client, alter OAuth errors, or weaken consent checks to work around them. Maintain the project in accordance with [Google's OAuth policies](https://developers.google.com/identity/protocols/oauth2/policies) and keep the public privacy commitments accurate.
