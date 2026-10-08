# Apni Website LIVE Karo — Step by Step (10 minute, koi coding nahi)

Ye guide tumhe **apni free website** banane me help karegi, jahan se tumhara
tool khud updates lega. Sab kuch browser me hoga — GitHub bilkul free hai.

## Step 1: GitHub account banao (2 minute)
1. **github.com** kholo → **Sign up** dabao
2. Email, password, username do (username yaad rakho — ye tumhari website ke
   link me aayega, misal: `hamza123`)
3. Email verify karo — bas, account ready!

## Step 2: Nayi repository banao (1 minute)
1. GitHub me upar **"+"** → **"New repository"**
2. Repository name likho: **`gsmtool`** (bilkul yehi naam)
3. **Public** select karo (Private par website free me live nahi hoti)
4. **"Add a README file"** par tick karo → **"Create repository"** dabao

## Step 3: Website files upload karo (3 minute)
1. Apni nayi repo kholo → **"Add file"** → **"Upload files"**
2. Ye **3 files** drag-drop karo (Muse ne tumhe di hain):
   - `index.html`
   - `version.json`
   - `HamzaGSMTool-v6.zip` (tool wali ZIP)
3. Neeche **"Commit changes"** dabao

## Step 4: version.json me apna username likho (2 minute)
1. Repo me **`version.json`** par click karo → **pencil icon** (Edit) dabao
2. `APNA-USERNAME` ki jagah **apna GitHub username** likho, misal:
   `https://hamza123.github.io/gsmtool/HamzaGSMTool-v6.zip`
3. **"Commit changes"** dabao

## Step 5: Website ON karo (2 minute)
1. Repo me **Settings** (upar tabs me) → left side **"Pages"**
2. "Build and deployment" me: Source = **"Deploy from a branch"**,
   Branch = **"main"**, folder = **"/ (root)"** → **Save**
3. 1-2 minute wait karo → tumhari website LIVE:
   **`https://APNA-USERNAME.github.io/gsmtool/`**
   (APNA-USERNAME ki jagah tumhara username)

## Step 6: Tool me link lagao (1 minute)
1. Tool kholo → **"⚙" (settings)** button → **"Check for Updates"** ke paas hai
2. Wahan ye URL paste karo:
   **`https://APNA-USERNAME.github.io/gsmtool/version.json`**
3. **Save** dabao → **"Test"** dabao — "latest hai" aana chahiye. DONE! 🎉

## Baad me update kaise doge? (jab naye models aayen)
1. Muse se nayi ZIP lo (misal `HamzaGSMTool-v7.zip`)
2. GitHub repo me **Upload files** se nayi ZIP dalo
3. `version.json` edit karo: `version` badlo (`"7.0"`), `download_url` me
   nayi ZIP ka naam likho, `notes` me likho kya naya hai
4. **Commit** → bas! Ab jis bhi PC par tool hai, wahan "Check for Updates"
   dabane par naya version khud aa jayega. Tumhe kisi ko ZIP bhejne ki
   zaroorat nahi!

## Muse se madad
Agar kahin atak jao to mujhe batao — main har step par guide karunga.
Apna GitHub username bana kar mujhe bata dena, main version.json tumhare
liye ready karke de dunga.
