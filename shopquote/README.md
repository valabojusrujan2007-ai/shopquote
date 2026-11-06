# ShopQuote

ShopQuote is a responsive browser app for workshop estimates. It can be opened directly from `index.html`, so drawing parsing, calculations, saved projects, and PDF quotation export work without installing a frontend toolchain.

## Run the app

- For local use, open `index.html` directly in a current browser. No Live Server or frontend toolchain is needed. Estimates and editable rate tables are saved in that browser's local storage.
- To publish with GitHub and Netlify, follow **GitHub and Netlify deployment** below. Netlify builds only the browser app into `dist/`; the Python backend is not part of this static deployment.
- Each device has its own saved estimates and settings. Static hosting does not synchronize data between devices. The included Python API can provide shared storage, but it currently has no login or access control; do not expose it publicly as-is.
- For ASCII and binary DXF analysis, use the server-backed workspace with Python 3.10 or newer. In PowerShell:

```powershell
cd .\backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8000
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000). The FastAPI service saves the workspace to SQLite by default and analyses DXF files with `ezdxf`. Set `SHOPQUOTE_DATABASE_URL` before starting the server to use PostgreSQL, for example:

```powershell
$env:SHOPQUOTE_DATABASE_URL = "postgresql+psycopg://shopquote:password@localhost:5432/shopquote"
uvicorn main:app --host 127.0.0.1 --port 8000
```

The browser app syncs its workspace to the API when served by ShopQuote. The database currently stores one workshop workspace as JSON; it is intended for a single workshop installation, not multi-tenant hosting. The API has no login or access control, so keep it on localhost or behind your workshop's trusted network controls.

## GitHub and Netlify deployment

The included `netlify.toml` publishes only the static browser app. Browser calculations, local estimates, PDF export and common ASCII DXF parsing work on the deployed site. Binary DXF upload needs the Python API. DWG conversion, STEP solid analysis and PDF dimension recognition still need separate processing services. The Python API is deliberately excluded from this public static deployment.

1. Install Git for Windows and GitHub Desktop, then sign in to GitHub Desktop.
2. In GitHub Desktop, choose **File > Add Local Repository** and select this `shopquote` folder. If it is not already a repository, choose the option to create one there. Name it `shopquote` and publish it to GitHub. Choose **Private** if you do not want the source repository to be publicly browsable; the deployed website itself remains public.
3. In Netlify, sign in with GitHub, choose **Add new site > Import an existing project**, authorize GitHub, and select the `shopquote` repository. Netlify reads `netlify.toml` for the build command and publish folder (`dist`). Deploy the site.
4. In Netlify's site settings, change the generated site name to `shopquote` if that name is available. The resulting URL will be `https://shopquote.netlify.app`; otherwise Netlify will provide another `*.netlify.app` URL. Netlify provisions HTTPS for the site.
5. GitHub Desktop will show changed files after edits. Commit and choose **Push origin**; Netlify automatically builds and publishes commits pushed to the connected production branch.

Do not commit `.env` files, API credentials, database files or workshop customer data. `.gitignore` excludes common local secrets, Python environments and database files. Do not deploy the included backend publicly until authentication and authorization have been added.

## What it does

- The ShopQuote server reads ASCII and binary DXF, expands block inserts and compound dimensions, and previews common line, arc, circle, polyline, spline, ellipse, hatch, face, and mesh geometry. It reads `$INSUNITS`, calculates XYZ bounds where geometry or DXF header extents are available, and shows an XY projection. Pan, zoom, and point-to-point measurement are available. Directly opening `index.html` without the server keeps the smaller browser parser for common ASCII entities.
- Uploading a drawing auto-fills the part name, dimensions, stock blank, material, compatible machining process and indicative price assumptions. Use **Auto-fill all details** for a one-click estimate without a drawing. For round stock it compares conventional and CNC turning; for plate or square stock it compares conventional and CNC milling, selecting the lowest estimated cost from setup, cycle time, batch quantity, and rates. Changing material, part dimensions, batch quantity, or saved shop rates refreshes the assumed form, blank and process. Workshop-entered material prices and operation rates take priority; defaults are editable and assumption-based estimates are saved for review.
- Lets the estimator correct the measured envelope and area. Missing critical inputs keep an estimate incomplete; automatically filled estimates remain marked indicative for review.
- Calculates stock volume for rectangular plate/flat stock, round bar, square bar, and hollow tube/pipe. Finished mass uses a CAD-reported volume when entered, or profile area × height. It calculates removed material, scrap credit, utilisation, operation costs, overhead, rejection allowance, profit margin, GST, and batch price.
- Auto-fill estimates a recyclable share and scrap value from the selected material, then applies the expected recovery credit to net material cost. The percentage and ₹/kg rate are editable; confirm both with your recycler.
- The operation step can auto-select a low-estimated-cost primary turning or milling process using **Auto-select easy process**. It estimates setup minutes from machine setup, workholding, drawing complexity, part size and material preparation, and shows the factor breakdown. Conventional and CNC options use separate low-cost placeholder rates, setup times and cycle-time assumptions when shop data is missing. Saved shop times/rates override assumptions where configured; these estimates still need confirmation against the actual fixture and part.
- Select INR, USD, EUR, GBP, JPY, CAD, AUD, SGD, CHF, CNY, AED or SAR in Settings. Exchange rates refresh automatically from [Frankfurter](https://frankfurter.dev/) once per day when the app opens or stays open; the exchange rate remains editable in Settings. Existing workshop prices and saved estimates convert with the workspace currency, and PDFs use its ISO code.
- Includes a searchable built-in catalog of 100+ common manufacturing materials across ferrous and non-ferrous metals, commodity and engineering plastics, elastomers, composites, ceramics and wood. Mapped metal assumptions track daily percentage moves in [Rzzro](https://rzzro.com/api/) commodity benchmarks, with fresh [Croncopia](https://croncopia.com/docs/commodity-source) indexes as fallback for steel HRC, aluminum, copper, nickel, zinc, lead and tin; stainless, brass and bronze use proxy blends. This preserves each material’s starting shop estimate while refreshing its market movement; it is not a local supplier quote. Other material assumptions and workshop-entered prices remain editable. Also includes machine rates, operation library, project save/edit/duplicate/delete, cost analysis, theme toggle, and generated quotation PDFs.

## Accuracy boundaries

- Closed-profile area is the sum of closed polylines and circles. Nested holes, overlapping profiles, blocks, and drawing topology need review. The browser app warns about this; correct the profile area from the engineering drawing before costing when required.
- DXF support is broad, but cannot guarantee geometry extraction from every application-specific or damaged file. Unsupported entities are reported after analysis. ACIS `3DSOLID`/`BODY` data and proxy objects are not reconstructed into faces or volume; a DXF header envelope may be shown when present. Enter volume from a CAD kernel or CAD application. An XY projection does not establish a part's solid volume.
- A 2D drawing does not fully specify machining depth, tolerance, workholding, setup, or cycle time. The app uses rough size/material/feature heuristics for suggested setup and cycle times; verify the selected route, fixture and times against the actual part.
- DWG needs a configured conversion provider; STEP solid analysis needs an Open CASCADE service; PDF dimension recognition needs a drawing extraction service. Those services are not configured here. The app identifies these formats and asks for validated manual dimensions rather than treating guesses as extracted measurements.
- When a material has no workshop price, auto-fill uses a low-cost illustrative placeholder. The catalog covers common manufacturing materials, not every alloy or substance; prices vary by grade, stock form, supplier, location and date. Scrap recovery rates, machine rates, overheads, GST, and margins are workshop-entered or placeholder assumptions. Confirm all rates and taxes before sending a quote.
- Exchange rates refresh from Frankfurter’s aggregated central-bank data and are reference values, not bank transaction rates. Metal indexes refresh from Rzzro’s public commodity API and fresh Croncopia data when available; the app ignores stale benchmark files and retains its last saved rates when offline. Both sources update independently, and material index movements do not represent the user’s local supplier price, stock form, alloy premium, GST or delivery cost.
- A few India material price anchors use published vendor or market references: commodity PP, HDPE, LDPE and PVC are around ₹95–₹96/kg ex works in the [September 2026 India Polymer Price Monitor](https://pramukhpolytech.com/polymer-prices/index.html); POM rods/sheets are listed at ₹185–₹380/kg by [Multi-Tech Polymers](https://multitechpolymers.in/products/delrin); PEEK stock is listed near ₹9,998/kg by [The Sahaj](https://www.thesahaj.co.in/engineering-plastics.html). Metal examples include SS 202 ₹145/kg, SS 304 ₹245/kg and SS 316 ₹390/kg from [Rajshree Stainless Steel's 2026 price table](https://www.rajshreestainlesssteel.com/stainless-steel-price-per-kg), and Grade 5 titanium plate from around ₹2,800/kg in this [2026 supplier reference](https://www.sachiyasteelintl.com/titanium-price.html). Form, grade, quantity, GST, transport and current supplier quotations can change these amounts; all other defaults are editable planning estimates, not live quotations.
- PDF files are generated client-side. No project, drawing, or quotation is sent to a third party by the static app.
