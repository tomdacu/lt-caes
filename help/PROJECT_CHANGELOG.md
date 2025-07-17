# Project Change Log & Version History

## 📋 Commit History Overview

This file contains a complete history of all commits to this project, along with instructions for navigating between versions.

### 🔄 How to Use This File
- **To see current commit:** `git log --oneline -1`
- **To revert to a specific commit:** `git checkout <commit-hash>`
- **To create a branch from old commit:** `git checkout -b <new-branch-name> <commit-hash>`
- **To go back to latest:** `git checkout main`
- **To see what changed in a commit:** `git show <commit-hash>`

---

## 📊 Complete Commit History

### Current Branch: main

**- f7ff78a | 2025-07-17 | Update exergetic analysis and documentation | Tommaso D'Acunzio | (HEAD -> main)**
- **Files changed:** exergetic_analysis.py, guida.md
- **Changes:** 16 insertions, 6 deletions
- **Description:** Updated exergetic analysis module and documentation

**- a677f1b | 2025-07-17 | Initial project setup | Tommaso D'Acunzio |**
- **Files added:** Complete project structure including:
  - Python modules: config.py, exergetic_analysis.py, main.py, parametric_analysis.py, plotting.py, specifications.py
  - Transformation package: compressor_formulas.py, exchanger.py, expander_formulas.py, storage.py
  - Documentation: guida.md
  - Compiled Python cache files

---

## 🎯 Quick Reference Commands

### Viewing History
```bash
# See all commits
git log --oneline --all --graph

# See detailed changes in last commit
git show HEAD

# See changes in specific commit
git show <commit-hash>

# See what files changed
git diff --name-only <commit-hash>~1 <commit-hash>
```

### Reverting Changes
```bash
# Revert to previous commit (temporary)
git checkout <commit-hash>

# Create new branch from old commit
git checkout -b restore-point-<commit-hash> <commit-hash>

# Reset current branch to previous commit (permanent)
git reset --hard <commit-hash>

# Revert specific commit (creates new commit)
git revert <commit-hash>
```

### File Recovery
```bash
# Restore specific file from previous commit
git checkout <commit-hash> -- <filename>

# See file content at specific commit
git show <commit-hash>:<filename>
```

---

## 📁 Current Project Structure (as of f7ff78a)

```
I_CAES/
├── config.py
├── exergetic_analysis.py
├── main.py
├── parametric_analysis.py
├── plotting.py
├── specifications.py
├── transformation/
│   ├── compressor_formulas.py
│   ├── exchanger.py
│   ├── expander_formulas.py
│   └── storage.py
└── help/                    # 📁 Cartella documentazione
    ├── guida.md             # Guida completa al programma
    ├── PROJECT_CHANGELOG.md # Storico versioni
    └── commit_history.log    # Log completo commit
```

---

## 📝 Last Updated
**Date:** 2025-07-17  
**Time:** 21:05:00 (Europe/Rome, UTC+2:00)  
**By:** Tommaso D'Acunzio  
**Changes:** Organizzati file di documentazione nella cartella 'help'

---

## 🔄 Next Steps
To update this file after new commits:
1. Run: `git log --oneline --all --graph --decorate --date=short --pretty=format:"- **%h** | %ad | %s | %an | %d" >> help/PROJECT_CHANGELOG.md`
2. Add the new commit details to the history section
3. Update the "Last Updated" section
