# 1. දැනට තියෙන පරණ Git settings අයින් කරලා අලුතෙන්ම පටන් ගන්න
rmdir /s /q .git
git init

# 2. GitHub repository එක ආයෙත් සම්බන්ධ කරන්න
git remote add origin https://github.com/Sithija-Kalhara/jarvis.git

# 3. GitHub එකේ දැනට තියෙන README එක local එකට ගන්න (මේක අනිවාර්යයි)
git pull origin main --rebase

# 4. දැන් ඔයාගේ ෆෝල්ඩරයේ තියෙන ඔක්කොම ෆයිල් ටික Git එකට එකතු කරන්න
git add .

# 5. Commit එකක් හදන්න
git commit -m "Initial manual push"

# 6. බලෙන්ම GitHub එකට push කරන්න (Force Push)
git push -u origin main --force