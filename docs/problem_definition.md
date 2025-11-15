# Problem Definition – Central Prompt Library

## Problem Summary
Teams maintain AI prompts and rules inside each repository, leading to:
- duplicated prompts across many codebases
- outdated or inconsistent versions
- difficulty updating rules in sync
- friction when switching between tools (Cursor, Claude Code, Codex, etc.)
- messy onboarding for new developers

Because prompts evolve quickly, embedding them inside individual repos causes **prompt drift**, **redundancy**, and **maintenance overhead**.

## Root Causes
- No centralized source of truth  
- AI tool ecosystems have inconsistent storage formats  
- Teams work across many repos, often copying prompts manually  
- Rules tied to repos but stored locally

## Impact
- Developers spend time hunting for or updating prompt snippets
- Multiple conflicting versions exist
- Poor standardization across the engineering org
- Slow propagation of improvements to prompts or rules

---

# Proposed Solution – A Centralized Prompt Library with Repo-Aware CLI

## Overview
Create a Python-based CLI tool (`prompt`) backed by a **central repository** of prompts and rules. Repos have only a tiny config file (`.promptlib.yml`) that references the central store without duplicating it.

The CLI:
- identifies the repo
- loads all relevant prompts + rules
- outputs them in a tool-agnostic format
- allows developers & agents to browse/run/search prompts
- synchronizes with the central store

## How It Solves the Problem
### **1. Single Source of Truth**
All prompts/rules live in one repo.  
No duplication. No drift.

### **2. Repo Awareness**
Rules/prompts can be tagged with associated repos.  
The CLI fetches the correct ones dynamically.

### **3. Tool Agnostic**
Prompts output in:
- raw text
- JSON
- block format  
usable by Claude Code, Cursor, Codex, etc.

### **4. Fast Updates**
A single change updates prompts for the entire organization.

### **5. Scalable & Extensible**
Support for:
- plugins  
- versioning  
- central registry  
- permissions  
- analytics  

---

# Who Benefits
- **Developers:** faster workflow + consistent prompts  
- **Teams:** unified standards and rules  
- **Org:** scalable AI-enabled development practices  

---

# Summary
The prompt library + CLI eliminates duplication, reduces maintenance burden, ensures consistency, and centralizes knowledge for all AI-assisted developer workflows.
