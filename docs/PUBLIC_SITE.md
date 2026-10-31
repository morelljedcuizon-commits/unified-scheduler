# Public website and GitHub Pages deployment

The website lives in `docs/public-site`. It is a buildless static site for the existing Windows desktop app, not a browser version of the scheduler. It uses local CSS, the app's visual identity and screenshots from the isolated demo workspace. It has no backend, JavaScript, tracking, external fonts or sign-in form. Technical documentation stays outside the deployed directory.

Files:

| File | Purpose |
| --- | --- |
| `index.html` | Product features, sample screenshots, practical limitations and a link to GitHub Releases |
| `privacy.html` | Data access, local storage, third-party requests, retention, removal and Limited Use commitments |
| `terms.html` | Basic application terms, MIT license relationship and service limitations |
| `styles.css` and `assets/` | Shared responsive styling, app icon and clearly labeled demo images |
| `.nojekyll` | Serve static files without a Jekyll build |

The publisher name **Unified Scheduler** and email **cuizon.morell@gmail.com** were provided by the developer. On October 31, 2026, the developer authorized website publication; the policy and terms now use that effective date and their draft notices have been removed. No custom domain has been supplied. Website publication does not assert Google verification approval.

## Published website

The [GitHub Pages deployment](https://github.com/morelljedcuizon-commits/unified-scheduler/actions/runs/41158584693) succeeded on October 31, 2026, for commit `7854fe2`. HTTPS is enforced. All three pages and their CSS, icon and screenshot assets returned HTTP 200 and matched the committed site files.

- Homepage: [Unified Scheduler](https://morelljedcuizon-commits.github.io/unified-scheduler/)
- [Privacy policy](https://morelljedcuizon-commits.github.io/unified-scheduler/privacy.html)
- [Terms of use](https://morelljedcuizon-commits.github.io/unified-scheduler/terms.html)

## Preview and review before publishing

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m http.server 8080 --bind 127.0.0.1 --directory docs/public-site
```

Visit `http://127.0.0.1:8080/`, `http://127.0.0.1:8080/privacy.html` and `http://127.0.0.1:8080/terms.html`. Press Ctrl+C to stop the server. A local preview is not a public OAuth application homepage.

Before publishing:

1. Review the policy and terms against the intended release and the publisher's actual practices. Verify that the supplied email is monitored. Obtain any legal review appropriate to your audience and jurisdiction.
2. Confirm the full OAuth scopes match `src/unified_scheduler/providers/google.py`, including the distinction between API responses and normalized event fields persisted locally. Check that source removal, token revocation and full-workspace removal instructions still match the app.
3. For future revisions, review the changes and update the actual policy/terms effective date. If preparing drafts, remove their `data-publication-draft` notices only when the publisher authorizes publication. The initial notices were removed following the October 31 publication instruction.
4. Review desktop and mobile layouts, keyboard focus, disclosure controls and all navigation. The download button links to the repository's releases listing rather than an invented package/version. Replace that link only with a release that actually exists and has been approved for publication.
5. Check that every screenshot contains only synthetic demo data. Keep the visible sample-data descriptions. Never copy a live calendar screenshot into this site.
6. Choose the final public domain and HTTPS URLs. Keep Google Console branding and policy links consistent with those URLs. Complete the separate [Google OAuth publication checklist](GOOGLE_OAUTH_PUBLICATION.md).

## Publish future website updates

The prepared `.github/workflows/pages.yml` workflow runs **only by manual dispatch**. Merely committing or pushing it does not deploy the website. It requires the owner's publication confirmation and rejects HTML that still contains a draft marker or an uppercase template placeholder.

1. Review and commit the website files, workflow and relevant documentation. Push them to the repository's default branch. No GitHub Release is created by the website workflow.
2. In the repository, open **Settings → Pages** and choose **GitHub Actions** as the build/deployment source. If repository or organization policies restrict Actions, allow the official checkout/Pages actions used by the workflow.
3. In **Settings → Environments**, review the `github-pages` environment's allowed branches and, if available for the repository plan, required reviewers. The workflow has only read access to contents, with Pages/OIDC deployment permissions scoped to the deploy job.
4. Open **Actions → Publish public website → Run workflow**, select the reviewed default branch and check the confirmation only after the legal pages and deployment are approved.
5. Confirm that both preparation and deployment succeeded. Use the URL reported by the deployment, not an assumed URL. Visit the homepage, privacy and terms directly in a signed-out browser and on a phone; all must be public over HTTPS.

The current deployment uses the project-site URL listed above. Relative links also support a custom domain without a site-generator rebuild.

The workflow uploads **only `docs/public-site`**. It does not publish the repository root, local configuration, databases, tokens, technical reports or desktop build artifacts. Check future edits before adding files to this directory.

See GitHub's official [custom Pages workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages) and [publishing-source settings](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).

## Custom domain and Google's separate ownership requirements

GitHub hosting and Google OAuth domain verification are separate. Publishing on `github.io` does not itself prove that the developer owns an appropriate top private domain for Google's branding requirements. Do not enter `github.io` as a developer-owned authorized domain.

For the predictable ownership route:

1. Register or use a domain the developer controls. Choose a public app hostname, such as `scheduler.your-owned-domain.example`; this is an illustration, not a supplied domain.
2. Verify that domain in the GitHub account's **Settings → Pages** using the DNS TXT record GitHub supplies. This helps protect the Pages domain association; it does not verify ownership with Google.
3. Set the intended hostname in the repository's **Settings → Pages → Custom domain**. Follow GitHub's current DNS instructions for that hostname. Use the exact CNAME or apex records documented by GitHub; do not copy guessed IP addresses. With an Actions deployment, configure the custom domain in Pages settings. No placeholder `CNAME` file is committed here.
4. Wait for DNS and certificate issuance, then enable **Enforce HTTPS**. Test all three pages on the custom hostname. Avoid wildcard DNS records.
5. Independently verify the owned domain in **Google Search Console** with an account associated with the correct Google Cloud project. A DNS Domain property is a useful way to prove control of the whole domain. Add the appropriate top private domain in Google Auth platform's authorized-domain settings and use the actual HTTPS homepage, privacy and terms URLs in Branding.
6. Submit the required branding and scope verification in Google Cloud. Website deployment, Search Console ownership and moving the OAuth audience to Production do not themselves grant Google's verification approval.

The default GitHub project URL can be useful for previewing public content, but it is not presented as sufficient proof for OAuth verification. Consult Google's current review guidance for the chosen hosting arrangement.

Official references: [GitHub custom-domain management](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/managing-a-custom-domain-for-your-github-pages-site), [GitHub domain verification](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/verifying-your-custom-domain-for-github-pages), [Google brand verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/brand-verification), and [Search Console ownership verification](https://support.google.com/webmasters/answer/9008080).

## Maintenance

Keep the site and app in agreement whenever scopes, data storage, external services, contact details or distribution behavior change. Do not remove the statement about pending Google verification until the actual project has the relevant approval. Revisit the [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy) before making changes to Google data use. Publishing policy text is a commitment to maintain the described practices, not evidence that compliance has been independently certified.
