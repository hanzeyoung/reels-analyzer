"""
main.py — 소상공인 릴스 분석 대시보드
실행: streamlit run main.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from pathlib import Path
import json
import random
import re
import os
import socket
import tempfile
import hashlib
import base64
import html
from urllib.parse import quote, urlencode

from app.api.gemini import (
    analyze_reel_from_file,
    analyze_reel_from_url,
    analyze_reel_from_thumbnail,
    analyze_reel_sequence_from_url,
    format_report,
    generate_revised_production_plan,
)
from app.api.meta_graph import build_oauth_url, collect_my_reels, exchange_authorization_code
from app.api.reels_collector import get_reel_from_url, get_top_reels as collect_top_reels
from app.core.audio_rights import annotate_tracks, save_rights_verification
from app.core.auth import auth_is_configured, delete_cloud_account, sign_in, sign_up
from app.core.config import get_env, get_env_bool, has_env
from app.core.content_projects import (
    PROJECT_STAGES,
    STAGE_LABELS,
    create_project,
    list_projects,
    next_action,
    pipeline_counts,
    update_project,
)
from app.core.storyboard import build_project_storyboard
from app.core.creator_memory import learn_creator_patterns, personalize_with_memory
from app.core.job_queue import cancel_job, enqueue_job, list_jobs
from app.core.market_watch import (
    build_market_alerts,
    build_market_snapshot,
    compare_snapshots,
    load_jsonl_history,
    load_watchlist,
    load_previous_snapshot,
    save_watch,
    save_snapshot,
)
from app.core.mobile_coach_server import ensure_mobile_coach_server
from app.core.performance_insights import (
    append_performance_snapshot,
    build_account_baseline,
    build_prediction_calibration,
    compare_measured_snapshots,
    compare_prediction_to_actual,
    load_performance_history,
    normalize_insights,
    performance_score,
)
from app.core.observability import get_daily_usage, init_error_tracking, load_recent_events
from app.core.privacy import delete_user_data, export_user_data
from app.core.token_vault import delete_encrypted_token, load_encrypted_token, save_encrypted_token
from app.db.supabase_client import configure_auth_session, save_analysis_for_instagram_media, sync_meta_account
from app.ui.workspace import render_workspace
from app.ui.appearance import appearance_controls, render_navigation

st.set_page_config(page_title="Reel Lab | 릴스 성장 워크스페이스", page_icon="🎬", layout="wide")
init_error_tracking("streamlit-app")

BASE_USER_REELS_DIR = Path("user_reels")
USER_REELS_DIR = BASE_USER_REELS_DIR
USER_REELS_LIBRARY = USER_REELS_DIR / "library.jsonl"
STORE_PROFILE_FILE = USER_REELS_DIR / "store_profile.json"

st.markdown("""
<style>
:root {
  --bg: #f7fafb;
  --surface: #ffffff;
  --surface-soft: #eef7f8;
  --text: #11181c;
  --muted: #607078;
  --border: #d9e2e5;
  --accent: #09cbea;
  --accent-strong: #007f94;
  --accent-contrast: #071216;
  --success: #16845b;
  --warning: #a66500;
  --danger: #c13b32;
  font-size: 16px;
}

html, body, [data-testid="stAppViewContainer"], .stApp {
  background: var(--bg);
  color: var(--text);
  font-family: Inter, Pretendard, "Noto Sans KR", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

.block-container {
  max-width: 82rem;
  padding-top: 4rem;
  padding-bottom: 4rem;
}

h1 { font-size: 2.4rem; line-height: 1.12; letter-spacing: 0; font-weight: 780; }
h2 { font-size: 1.55rem; }
h3 { font-size: 1.15rem; }
h2, h3 { line-height: 1.3; letter-spacing: 0; color: var(--text); }

p, li, label, [data-testid="stMarkdownContainer"] {
  font-size: 1rem;
  line-height: 1.6;
}

button, [role="button"], input, textarea, select {
  min-height: 2.75rem;
  font-size: 1rem !important;
}

[data-testid="stHeader"] {
  background: rgba(247, 250, 251, 0.92);
  border-bottom: 1px solid var(--border);
}

[data-testid="stSidebar"] {
  background: #ffffff;
  border-right: 1px solid var(--border);
}

[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
  color: var(--muted);
}

[data-testid="stSidebar"] [role="radiogroup"] {
  gap: 0.35rem;
}

[data-testid="stSidebar"] [role="radiogroup"] label {
  border: 1px solid transparent;
  border-radius: 0.5rem;
  padding: 0.55rem 0.65rem;
  transition: background 120ms ease, border-color 120ms ease;
}

[data-testid="stSidebar"] [role="radiogroup"] label:hover {
  background: var(--surface-soft);
  border-color: #c6eaef;
}

[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
  background: #e7fafd;
  border-color: #91e7f2;
  color: var(--text);
  font-weight: 750;
}

[data-testid="stSidebar"] [data-baseweb="radio"] > div:first-child {
  display: none;
}

.brand-lockup {
  display: flex;
  align-items: center;
  gap: 0.7rem;
  margin: 0.15rem 0 1.4rem;
}

.brand-mark {
  width: 2.1rem;
  height: 2.1rem;
  display: grid;
  place-items: center;
  border-radius: 0.45rem;
  background: var(--accent);
  color: var(--accent-contrast);
  font-size: 1rem;
  font-weight: 900;
}

.brand-name {
  color: var(--text);
  font-size: 1.08rem;
  font-weight: 850;
  line-height: 1.1;
}

.brand-sub {
  color: var(--muted);
  font-size: 0.72rem;
  margin-top: 0.12rem;
}

.service-status {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  color: var(--muted);
  font-size: 0.78rem;
  margin: 0.35rem 0;
}

.status-dot {
  width: 0.45rem;
  height: 0.45rem;
  border-radius: 50%;
  background: var(--success);
}

.status-dot.off { background: var(--danger); }

.page-kicker, .workspace-kicker {
  color: var(--accent-strong);
  font-size: 0.73rem;
  font-weight: 850;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  margin-bottom: 0.65rem;
}

.page-heading {
  padding-bottom: 1.4rem;
  border-bottom: 1px solid var(--border);
  margin-bottom: 1.55rem;
}

.page-heading h1, .workspace-header h1 {
  margin: 0;
  color: var(--text);
}

.page-heading p, .workspace-header p {
  margin: 0.6rem 0 0;
  color: var(--muted);
  max-width: 48rem;
}

.workspace-header {
  padding: 0.4rem 0 1.8rem;
  display: flex;
  justify-content: space-between;
  gap: 2rem;
  align-items: end;
}

.workspace-header h1 {
  max-width: 42rem;
  font-size: 2.75rem;
}

.workspace-pulse {
  min-width: 12rem;
  padding: 0.85rem 1rem;
  border-left: 3px solid var(--accent);
  background: var(--surface);
}

.workspace-pulse strong { display: block; font-size: 1.35rem; }
.workspace-pulse span { color: var(--muted); font-size: 0.78rem; }

.workflow-strip {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  border: 1px solid var(--border);
  background: var(--surface);
  margin-bottom: 2rem;
}

.workflow-step {
  min-height: 5.4rem;
  padding: 1rem;
  border-right: 1px solid var(--border);
}

.workflow-step:last-child { border-right: 0; }
.workflow-step.active { box-shadow: inset 0 3px 0 var(--accent); }
.workflow-num { color: var(--accent-strong); font-size: 0.7rem; font-weight: 850; }
.workflow-title { display: block; margin-top: 0.3rem; font-weight: 800; }
.workflow-copy { color: var(--muted); font-size: 0.78rem; margin-top: 0.18rem; }

[data-testid="stButton"] button,
[data-testid="stLinkButton"] a,
[data-testid="stDownloadButton"] button,
[data-testid="stFormSubmitButton"] button {
  border-radius: 0.45rem;
  border-color: #b9c9ce;
  background: #ffffff;
  color: var(--text);
  font-weight: 750;
  box-shadow: none;
}

[data-testid="stButton"] button:hover,
[data-testid="stLinkButton"] a:hover,
[data-testid="stDownloadButton"] button:hover,
[data-testid="stFormSubmitButton"] button:hover {
  border-color: var(--accent-strong);
  color: #005f70;
  background: #f2fdff;
}

[data-testid="stButton"] button[kind="primary"],
[data-testid="stFormSubmitButton"] button[kind="primary"] {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--accent-contrast);
}

[data-testid="stMetric"] {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  padding: 1rem 1.1rem;
  min-height: 7.4rem;
}

[data-testid="stMetricLabel"] { color: var(--muted); }
[data-testid="stMetricValue"] { color: var(--text); font-weight: 780; }

[data-baseweb="tab-list"] {
  gap: 1.3rem;
  border-bottom: 1px solid var(--border);
}

[data-baseweb="tab"] {
  padding-left: 0;
  padding-right: 0;
  color: var(--muted);
}

[aria-selected="true"][data-baseweb="tab"] {
  color: var(--text);
  font-weight: 800;
}

[data-baseweb="tab-highlight"] { background: var(--accent) !important; }

[data-testid="stFileUploaderDropzone"] {
  border: 1px dashed #8dcfd9;
  border-radius: 0.5rem;
  background: #f5fdfe;
  min-height: 10rem;
}

[data-testid="stDataFrame"], [data-testid="stPlotlyChart"] {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  overflow: hidden;
}

[data-testid="stExpander"] {
  background: var(--surface);
  border-color: var(--border);
  border-radius: 0.5rem;
}

[data-testid="stAlert"] {
  border-radius: 0.5rem;
  border-width: 1px;
}

button:focus-visible,
[role="button"]:focus-visible,
input:focus-visible,
textarea:focus-visible,
select:focus-visible,
[data-baseweb="radio"] :focus-visible {
  outline: 0.1875rem solid var(--accent) !important;
  outline-offset: 0.1875rem !important;
  box-shadow: none !important;
}

.hook-tag {
  background: #e8fbfd;
  color: var(--accent-strong);
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  padding: 0.375rem 0.625rem;
  font-size: 0.9375rem;
  margin: 0.125rem;
  display: inline-block;
}

.shot-card {
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  background: var(--surface);
  padding: 1rem;
  margin: 0.25rem 0 0.75rem;
}

.phone-frame {
  width: min(100%, 15rem);
  aspect-ratio: 9 / 16;
  margin: 0 auto 0.75rem;
  border: 0.1875rem solid var(--text);
  border-radius: 1rem;
  background:
    linear-gradient(90deg, transparent 33%, rgba(36,87,214,0.28) 33%, rgba(36,87,214,0.28) 34%, transparent 34%, transparent 66%, rgba(36,87,214,0.28) 66%, rgba(36,87,214,0.28) 67%, transparent 67%),
    linear-gradient(0deg, transparent 33%, rgba(36,87,214,0.28) 33%, rgba(36,87,214,0.28) 34%, transparent 34%, transparent 66%, rgba(36,87,214,0.28) 66%, rgba(36,87,214,0.28) 67%, transparent 67%),
    #ffffff;
  position: relative;
  overflow: hidden;
}

.phone-frame::before {
  content: "휴대폰 화면";
  position: absolute;
  top: 0.35rem;
  left: 0;
  right: 0;
  text-align: center;
  color: var(--muted);
  font-size: 0.75rem;
}

.plate, .cup, .hand, .subject, .face, .counter, .path-line {
  position: absolute;
  border: 0.125rem solid var(--accent);
  background: rgba(36,87,214,0.12);
}

.plate {
  width: 46%;
  aspect-ratio: 1;
  border-radius: 50%;
  left: 27%;
  top: 38%;
}

.cup {
  width: 20%;
  aspect-ratio: 1;
  border-radius: 50%;
  right: 17%;
  top: 23%;
}

.hand {
  width: 26%;
  height: 12%;
  border-radius: 999px;
  left: 37%;
  bottom: 12%;
  transform: rotate(-18deg);
}

.subject {
  width: 70%;
  height: 42%;
  border-radius: 1rem;
  left: 15%;
  top: 29%;
}

.face {
  width: 30%;
  aspect-ratio: 1;
  border-radius: 50%;
  left: 35%;
  top: 18%;
}

.counter {
  width: 74%;
  height: 18%;
  left: 13%;
  bottom: 16%;
  border-radius: 0.75rem;
}

.path-line {
  width: 0.25rem;
  height: 58%;
  left: 50%;
  top: 23%;
  border: none;
  background: var(--accent);
}

.shot-label {
  position: absolute;
  color: var(--text);
  font-size: 0.75rem;
  font-weight: 700;
  background: rgba(255,255,255,0.86);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 0.125rem 0.375rem;
}

.label-main { left: 50%; top: 51%; transform: translate(-50%, -50%); }
.label-side { right: 10%; top: 19%; }
.label-bottom { left: 34%; bottom: 8%; }
.label-top { left: 36%; top: 13%; }
.label-center { left: 50%; top: 48%; transform: translate(-50%, -50%); }
.label-path { left: 54%; top: 44%; }

.storyboard-card {
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  background: var(--surface);
  padding: 1rem;
  margin: 0.5rem 0 1rem;
}

.timeline-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(9.5rem, 1fr));
  gap: .65rem;
  margin: .35rem 0 .8rem;
}

.timeline-card {
  min-height: 7.25rem;
  padding: .8rem;
  border: 1px solid var(--border);
  border-radius: .8rem;
  background: linear-gradient(145deg, rgba(9,203,234,.08), var(--surface) 46%);
  box-shadow: 0 .35rem 1rem rgba(21,54,61,.05);
}

.timeline-card span {
  display: inline-block;
  margin-bottom: .55rem;
  padding: .18rem .45rem;
  border-radius: 999px;
  background: var(--accent);
  color: #fff;
  font-size: .72rem;
  font-weight: 850;
}

.timeline-card p {
  margin: 0;
  color: var(--text);
  font-size: .9rem;
  font-weight: 700;
  line-height: 1.45;
}

.timeline-empty {
  padding: 1rem;
  border: 1px dashed var(--border);
  border-radius: .75rem;
  color: var(--muted);
  text-align: center;
}

.storyboard-title {
  font-size: 1rem;
  font-weight: 800;
  margin-bottom: 0.5rem;
}

.story-phone {
  width: min(100%, 13rem);
  aspect-ratio: 9 / 16;
  margin: 0 auto 0.75rem;
  border: 0.1875rem solid var(--text);
  border-radius: 1rem;
  background:
    linear-gradient(90deg, transparent 33%, rgba(36,87,214,0.2) 33%, rgba(36,87,214,0.2) 34%, transparent 34%, transparent 66%, rgba(36,87,214,0.2) 66%, rgba(36,87,214,0.2) 67%, transparent 67%),
    linear-gradient(0deg, transparent 33%, rgba(36,87,214,0.2) 33%, rgba(36,87,214,0.2) 34%, transparent 34%, transparent 66%, rgba(36,87,214,0.2) 66%, rgba(36,87,214,0.2) 67%, transparent 67%),
    #fffdf8;
  overflow: hidden;
  position: relative;
}

.story-phone.has-depth::before {
  content: "";
  position: absolute;
  left: -18%; right: -18%; bottom: -12%; height: 58%;
  background:
    repeating-linear-gradient(90deg, rgba(36,87,214,.13) 0 1px, transparent 1px 16%),
    repeating-linear-gradient(0deg, rgba(36,87,214,.13) 0 1px, transparent 1px 16%);
  transform: perspective(12rem) rotateX(58deg);
  transform-origin: bottom;
  z-index: 0;
  pointer-events: none;
}

.story-motion-badge {
  position: absolute;
  top: .45rem; right: .45rem; z-index: 5;
  border-radius: 999px;
  padding: .2rem .45rem;
  color: #fff;
  background: rgba(13,18,28,.82);
  font-size: .66rem;
  font-weight: 850;
  box-shadow: 0 .2rem .7rem rgba(0,0,0,.16);
}

.story-subtitle {
  position: absolute;
  left: 8%;
  right: 8%;
  padding: 0.35rem 0.5rem;
  border-radius: 0.45rem;
  color: #ffffff;
  background: rgba(13, 18, 28, 0.84);
  font-size: 0.72rem;
  font-weight: 800;
  line-height: 1.25;
  text-align: center;
  box-shadow: 0 0.25rem 1rem rgba(0,0,0,0.18);
  z-index: 4;
}

.subtitle-top { top: 12%; }
.subtitle-mid { top: 46%; }
.subtitle-bottom { bottom: 12%; }
.subtitle-accent { background: #09cbea; color: #071216; }
.subtitle-light { background: rgba(255,255,255,0.9); color: #11181c; border: 1px solid var(--border); }

.story-scene {
  position: absolute;
  border: 0.15rem solid var(--accent);
  background: rgba(36,87,214,0.14);
  z-index: 1;
}

.story-motion {
  will-change: left, top, width, height;
}

@media (prefers-reduced-motion: reduce) {
  .story-motion { animation: none; }
}

.story-focus-point {
  position: absolute;
  border: 0.2rem solid #ff5a36;
  border-radius: 50%;
  background: rgba(255,90,54,0.14);
  color: #ffffff;
  font-size: 0.62rem;
  font-weight: 900;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  text-shadow: 0 1px 3px rgba(0,0,0,0.8);
  z-index: 2;
}

.story-scene-label {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  width: 90%;
  color: var(--accent);
  font-size: 0.68rem;
  font-weight: 800;
  text-align: center;
}

.scene-cta { background: rgba(20,108,67,0.16); border-color: var(--success); }
.scene-cta .story-scene-label { color: var(--success); }

.scene-hero {
  width: 58%;
  aspect-ratio: 1;
  border-radius: 50%;
  left: 21%;
  top: 34%;
}

.scene-close {
  width: 82%;
  height: 46%;
  border-radius: 1rem;
  left: 9%;
  top: 31%;
}

.scene-space {
  width: 78%;
  height: 44%;
  border-radius: 1rem;
  left: 11%;
  top: 28%;
}

.scene-hand {
  width: 34%;
  height: 10%;
  border-radius: 999px;
  left: 34%;
  bottom: 19%;
  transform: rotate(-18deg);
}

.scene-cta {
  width: 72%;
  height: 28%;
  border-radius: 0.8rem;
  left: 14%;
  top: 36%;
  background: rgba(20,108,67,0.16);
  border-color: var(--success);
}

.story-note {
  margin: 0.25rem 0;
  color: var(--text);
  font-size: 0.95rem;
  line-height: 1.5;
}

.motion-guide {
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  background: var(--surface);
  padding: 1rem;
  margin: 0.5rem 0 1rem;
}

.motion-phone {
  width: min(100%, 17rem);
  aspect-ratio: 9 / 16;
  margin: 0 auto 0.75rem;
  border: 0.1875rem solid var(--text);
  border-radius: 1rem;
  background:
    linear-gradient(90deg, transparent 33%, rgba(36,87,214,0.18) 33%, rgba(36,87,214,0.18) 34%, transparent 34%, transparent 66%, rgba(36,87,214,0.18) 66%, rgba(36,87,214,0.18) 67%, transparent 67%),
    linear-gradient(0deg, transparent 33%, rgba(36,87,214,0.18) 33%, rgba(36,87,214,0.18) 34%, transparent 34%, transparent 66%, rgba(36,87,214,0.18) 66%, rgba(36,87,214,0.18) 67%, transparent 67%),
    #fffdf8;
  overflow: hidden;
  position: relative;
}

.motion-scene {
  position: absolute;
  inset: 0;
  opacity: 0;
  animation: sceneCycle 15s infinite;
}

.motion-scene:nth-child(1) { animation-delay: 0s; }
.motion-scene:nth-child(2) { animation-delay: 3s; }
.motion-scene:nth-child(3) { animation-delay: 6s; }
.motion-scene:nth-child(4) { animation-delay: 9s; }
.motion-scene:nth-child(5) { animation-delay: 12s; }

.motion-object {
  position: absolute;
  border: 0.15rem solid var(--accent);
  background: rgba(36,87,214,0.14);
  box-shadow: 0 0.35rem 1rem rgba(36,87,214,0.15);
}

.motion-plate {
  width: 46%;
  aspect-ratio: 1;
  border-radius: 50%;
  left: 27%;
  top: 38%;
  animation: plateMove 3s ease-in-out infinite;
}

.motion-close {
  width: 56%;
  height: 32%;
  border-radius: 1rem;
  left: 22%;
  top: 36%;
  animation: zoomMove 3s ease-in-out infinite;
}

.motion-space {
  width: 78%;
  height: 38%;
  border-radius: 1rem;
  left: 11%;
  top: 30%;
  animation: panMove 3s ease-in-out infinite;
}

.motion-hand {
  width: 30%;
  height: 9%;
  border-radius: 999px;
  left: 4%;
  bottom: 20%;
  transform: rotate(-18deg);
  animation: handMove 3s ease-in-out infinite;
}

.motion-cta {
  width: 72%;
  height: 30%;
  border-color: var(--success);
  background: rgba(20,108,67,0.16);
  border-radius: 0.9rem;
  left: 14%;
  top: 36%;
  animation: holdMove 3s ease-in-out infinite;
}

.motion-caption {
  position: absolute;
  left: 8%;
  right: 8%;
  padding: 0.35rem 0.5rem;
  border-radius: 0.45rem;
  background: rgba(13,18,28,0.84);
  color: #fff;
  font-size: 0.72rem;
  font-weight: 850;
  line-height: 1.25;
  text-align: center;
  animation: captionPop 3s ease-in-out infinite;
}

.motion-caption.top { top: 12%; background: #09cbea; color: #071216; }
.motion-caption.mid { top: 46%; background: rgba(255,255,255,0.92); color: #11181c; border: 1px solid var(--border); }
.motion-caption.bottom { bottom: 12%; }

.motion-step {
  position: absolute;
  left: 0.5rem;
  top: 0.5rem;
  color: var(--accent);
  background: rgba(255,255,255,0.9);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 0.2rem 0.45rem;
  font-size: 0.75rem;
  font-weight: 850;
}

@keyframes sceneCycle {
  0%, 100% { opacity: 0; }
  4%, 16% { opacity: 1; }
  20% { opacity: 0; }
}

@keyframes plateMove {
  0% { transform: translate(-18%, 8%) scale(0.82); }
  50% { transform: translate(0, 0) scale(1); }
  100% { transform: translate(0, 0) scale(1); }
}

@keyframes zoomMove {
  0% { transform: scale(0.78); }
  55% { transform: scale(1.28); }
  100% { transform: scale(1.28); }
}

@keyframes panMove {
  0% { transform: translateX(-12%); }
  55% { transform: translateX(10%); }
  100% { transform: translateX(10%); }
}

@keyframes handMove {
  0% { transform: translateX(-25%) rotate(-18deg); }
  55% { transform: translateX(135%) rotate(-18deg); }
  100% { transform: translateX(135%) rotate(-18deg); }
}

@keyframes holdMove {
  0% { transform: scale(0.94); }
  55% { transform: scale(1); }
  100% { transform: scale(1); }
}

@keyframes captionPop {
  0% { opacity: 0; transform: translateY(0.5rem); }
  35% { opacity: 1; transform: translateY(0); }
  100% { opacity: 1; transform: translateY(0); }
}

.home-card {
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  background: var(--surface);
  padding: 1.2rem;
  min-height: 12.5rem;
  box-shadow: 0 0.75rem 2.5rem rgba(21, 54, 61, 0.06);
}

.home-icon {
  width: 2.25rem;
  height: 2.25rem;
  display: grid;
  place-items: center;
  font-size: 1.15rem;
  line-height: 1;
  margin-bottom: 1.1rem;
  border-radius: 0.4rem;
  background: #e3fafc;
}

.home-title {
  font-weight: 850;
  font-size: 1.15rem;
  margin-bottom: 0.45rem;
}

.home-desc {
  color: var(--muted);
  font-size: 0.95rem;
  line-height: 1.45;
}

.loop-card {
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  margin-top: 1rem;
}

.loop-item { padding: 1.2rem 0.8rem; position: relative; }
.loop-item:not(:last-child)::after {
  content: "→";
  position: absolute;
  right: -0.15rem;
  top: 1.25rem;
  color: #9babb0;
}
.loop-item b { display: block; color: var(--text); font-size: 0.9rem; }
.loop-item span { color: var(--muted); font-size: 0.72rem; }

@media (max-width: 48rem) {
  .block-container {
    padding-left: 1rem;
    padding-right: 1rem;
  }

  [data-testid="column"] {
    flex: 1 1 100% !important;
    min-width: 100% !important;
  }

  [data-testid="stMetric"] {
    padding-block: 0.5rem;
  }

  .workspace-header { display: block; }
  .workspace-header h1 { font-size: 2rem; }
  .workspace-pulse { margin-top: 1rem; }
  .workflow-strip { grid-template-columns: 1fr 1fr; }
  .workflow-step:nth-child(2) { border-right: 0; }
  .workflow-step:nth-child(-n+2) { border-bottom: 1px solid var(--border); }
  .loop-card { grid-template-columns: 1fr 1fr 1fr; }
  .loop-item:nth-child(3)::after { display: none; }
}
</style>
""", unsafe_allow_html=True)


def enforce_app_login() -> str:
    if not get_env_bool("REQUIRE_APP_LOGIN", False):
        configure_auth_session()
        return ""

    if not auth_is_configured():
        st.error("로그인을 사용하려면 SUPABASE_URL과 SUPABASE_ANON_KEY를 설정해야 합니다.")
        st.stop()

    auth_session = st.session_state.get("app_auth") or {}
    if auth_session.get("access_token") and auth_session.get("refresh_token"):
        configure_auth_session(auth_session["access_token"], auth_session["refresh_token"])
        return str(auth_session.get("user_id") or "")

    st.markdown(
        """
        <div class="page-heading">
          <div class="page-kicker">SECURE WORKSPACE</div>
          <h1>Reel Lab 로그인</h1>
          <p>매장 데이터와 Instagram 분석 결과를 계정별로 안전하게 분리합니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    login_tab, signup_tab = st.tabs(["로그인", "계정 만들기"])
    with login_tab:
        with st.form("app_login_form"):
            email = st.text_input("이메일", key="login_email")
            password = st.text_input("비밀번호", type="password", key="login_password")
            login_submit = st.form_submit_button("로그인", type="primary", use_container_width=True)
        if login_submit:
            try:
                st.session_state["app_auth"] = sign_in(email.strip(), password)
                st.rerun()
            except Exception as exc:
                st.error(f"로그인 실패: {exc}")

    with signup_tab:
        with st.form("app_signup_form"):
            signup_email = st.text_input("이메일", key="signup_email")
            signup_password = st.text_input("비밀번호", type="password", key="signup_password")
            signup_confirm = st.text_input("비밀번호 확인", type="password", key="signup_confirm")
            signup_submit = st.form_submit_button("계정 만들기", use_container_width=True)
        if signup_submit:
            if len(signup_password) < 8:
                st.error("비밀번호는 8자 이상이어야 합니다.")
            elif signup_password != signup_confirm:
                st.error("비밀번호 확인이 일치하지 않습니다.")
            else:
                try:
                    payload = sign_up(signup_email.strip(), signup_password)
                    if payload:
                        st.session_state["app_auth"] = payload
                        st.rerun()
                    st.success("계정을 만들었습니다. 이메일 확인 후 로그인해주세요.")
                except Exception as exc:
                    st.error(f"계정 생성 실패: {exc}")
    st.stop()


AUTH_USER_ID = enforce_app_login()
if AUTH_USER_ID:
    user_namespace = hashlib.sha256(AUTH_USER_ID.encode("utf-8")).hexdigest()[:20]
    USER_REELS_DIR = BASE_USER_REELS_DIR / user_namespace
    USER_REELS_LIBRARY = USER_REELS_DIR / "library.jsonl"
    STORE_PROFILE_FILE = USER_REELS_DIR / "store_profile.json"
JOB_DB_PATH = BASE_USER_REELS_DIR / "jobs.sqlite3"
JOB_OWNER_ID = AUTH_USER_ID or "local"
AUDIO_RIGHTS_REGISTRY = USER_REELS_DIR / "audio_rights_registry.json"
MARKET_WATCHLIST_PATH = USER_REELS_DIR / "market_watchlist.json"
MARKET_SNAPSHOT_DIR = USER_REELS_DIR / "market_snapshots"
MARKET_DELIVERY_HISTORY = USER_REELS_DIR / "market_delivery_history.jsonl"
META_TOKEN_VAULT = USER_REELS_DIR / "meta_token.enc"
CONTENT_PROJECTS_PATH = USER_REELS_DIR / "content_projects.json"


def shorten_text(value: str, limit: int = 64) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def first_caption_line(caption: str) -> str:
    for line in str(caption or "").splitlines():
        cleaned = line.strip(" -_·")
        if cleaned:
            return cleaned
    return "내용 설명 없음"


def make_reel_title(entry: dict, btype: str) -> str:
    caption = str(entry.get("caption", ""))
    terms = [term for term in (entry.get("matched_keyword_terms") or []) if term]

    if terms:
        useful_terms = [
            term for term in terms
            if len(term) >= 2 and term not in {"성수동카페", "성수동", "성수"}
        ]
        if useful_terms:
            return shorten_text(f"{useful_terms[0]} 인기 릴스", 18)

    title_patterns = [
        ("소금빵", "소금빵 맛집"),
        ("수플레", "수플레 팬케이크"),
        ("말차", "말차 디저트"),
        ("브런치", "브런치 메뉴"),
        ("팝업", "성수 팝업 코스"),
        ("연말", "성수 연말 놀거리"),
        ("카페", "신상 카페 소개"),
        ("베이커리", "베이커리 카페"),
        ("디저트", "디저트 추천"),
        ("커피", "커피 메뉴"),
        ("맛집", "맛집 추천"),
        ("네일", "네일 전후"),
        ("피부", "피부 관리"),
        ("코디", "코디 추천"),
        ("운동", "운동 자세"),
        ("필라테스", "필라테스 교정"),
    ]
    for keyword, title in title_patterns:
        if keyword in caption:
            return title

    username = entry.get("username")
    if username:
        return shorten_text(f"@{username} 참고 릴스", 18)
    return f"{btype} 참고 릴스"


def describe_reel(entry: dict, btype: str) -> str:
    terms = entry.get("matched_keyword_terms") or []
    if terms:
        return shorten_text(f"{', '.join(terms[:3])} 관련 릴스 · @{entry.get('username') or 'unknown'}", 72)

    caption = str(entry.get("caption", ""))
    keywords = {
        "카페": ["커피", "디저트", "빵", "수플레", "말차", "카페"],
        "식당": ["맛집", "메뉴", "고기", "파스타", "라멘", "국밥"],
        "뷰티": ["네일", "피부", "메이크업", "속눈썹"],
        "패션": ["코디", "룩북", "신상", "스타일"],
        "운동/헬스": ["운동", "헬스", "필라테스", "PT"],
    }.get(btype, [btype])
    matched = [word for word in keywords if word and word in caption]
    if matched:
        return shorten_text(f"{', '.join(matched[:2])} 장면을 중심으로 보여주는 릴스", 72)
    return shorten_text(f"{btype} 업종 참고용 릴스 · @{entry.get('username') or 'unknown'}", 72)


def load_download_log_reels(btype: str) -> list[dict]:
    rows = []
    seen_codes = set()
    for log_path in sorted(Path(".").glob("videos_verify*/download_log.jsonl")):
        try:
            lines = log_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue

        for line in lines:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            code = entry.get("code") or entry.get("id")
            if not code or code in seen_codes:
                continue
            seen_codes.add(code)

            caption = entry.get("caption", "")
            score = float(entry.get("rank_score") or 0)
            rows.append({
                "릴스": code,
                "릴스명": make_reel_title(entry, btype),
                "어떤 영상인지": describe_reel(entry, btype),
                "원문": shorten_text(first_caption_line(caption), 54),
                "캡션": caption,
                "링크": entry.get("url") or f"https://www.instagram.com/reel/{code}/",
                "로컬영상": entry.get("local_video_path", ""),
                "사용자": entry.get("username") or "",
                "출처": "실제 수집",
                "업종": btype,
                "조회수": int(entry.get("ig_play_count") or 0),
                "좋아요": int(entry.get("like_count") or 0),
                "저장": 0,
                "공유": int(entry.get("share_count") or 0),
                "총점": round(min(score * 8.2, 100), 1),
                "등급": "S" if score >= 10 else ("A" if score >= 8 else "B"),
                "_rank_score": score,
                "길이(초)": int(entry.get("video_duration") or random.choice([15, 20, 30, 45, 60])),
                "촬영구도": random.choice(["탑뷰", "클로즈업", "팔로잉샷", "정면샷"]),
                "BGM": random.choice(["신나는", "감성적", "조용한"]),
                "BGM곡": entry.get("audio_title") or "",
                "analysis": entry.get("analysis") or {},
                "insights": normalize_insights(entry),
                "업로드": datetime.now() - timedelta(days=random.randint(1, 60)),
            })
    rows.sort(key=lambda row: row.get("_rank_score", 0), reverse=True)
    for index, row in enumerate(rows):
        row["총점"] = round(max(86, 100 - index * 3.0), 1)
        row["등급"] = "S" if row["총점"] >= 90 else "A"
    return rows


def load_user_reels(btype: str) -> list[dict]:
    if not USER_REELS_LIBRARY.exists():
        return []

    rows = []
    try:
        lines = USER_REELS_LIBRARY.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        if entry.get("업종") and entry.get("업종") != btype:
            continue

        local_video = entry.get("로컬영상", "")
        rows.append({
            "릴스": entry.get("릴스") or Path(local_video).stem,
            "릴스명": entry.get("릴스명") or f"{btype} 참고 릴스",
            "어떤 영상인지": entry.get("어떤 영상인지") or f"{btype} 업종 직접 추가 릴스",
            "원문": entry.get("원문") or entry.get("릴스명") or "",
            "캡션": entry.get("캡션") or "",
            "링크": entry.get("링크") or "",
            "로컬영상": local_video,
            "원격영상": entry.get("원격영상") or "",
            "썸네일": entry.get("썸네일") or "",
            "사용자": entry.get("사용자") or entry.get("username") or "",
            "출처": entry.get("출처") or "직접 추가",
            "업종": btype,
            "조회수": int(entry.get("조회수") or 0),
            "좋아요": int(entry.get("좋아요") or 0),
            "저장": int(entry.get("저장") or 0),
            "공유": int(entry.get("공유") or 0),
            "총점": float(entry.get("총점") or 70),
            "등급": entry.get("등급") or "B",
            "길이(초)": int(entry.get("길이(초)") or 0),
            "촬영구도": entry.get("촬영구도") or "-",
            "BGM": entry.get("BGM") or "-",
            "BGM곡": entry.get("BGM곡") or "",
            "analysis": entry.get("analysis") or {},
            "insights": entry.get("insights") or {},
            "instagram_media_id": entry.get("instagram_media_id") or "",
            "store_id": entry.get("store_id") or "",
            "업로드": datetime.fromisoformat(entry["업로드"]) if entry.get("업로드") else datetime.now(),
        })
    return rows


def append_user_reel(entry: dict) -> None:
    USER_REELS_DIR.mkdir(exist_ok=True)
    with USER_REELS_LIBRARY.open("a", encoding="utf-8") as file:
        file.write(json.dumps(entry, ensure_ascii=False) + "\n")


def make_store_id(profile: dict) -> str:
    identity = "|".join([
        str(profile.get("name") or "").strip().lower(),
        str(profile.get("place") or "").strip().lower(),
        str(profile.get("menu") or "").strip().lower(),
    ])
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16] if identity.strip("|") else "default"


def load_store_profile() -> dict:
    if not STORE_PROFILE_FILE.exists():
        return {}
    try:
        return json.loads(STORE_PROFILE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_store_profile(profile: dict) -> dict:
    USER_REELS_DIR.mkdir(exist_ok=True)
    stored = {**profile, "store_id": profile.get("store_id") or make_store_id(profile)}
    STORE_PROFILE_FILE.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
    return stored


def upsert_user_reel(entry: dict) -> None:
    """Replace a local library row by reel id or permalink while preserving other rows."""
    USER_REELS_DIR.mkdir(exist_ok=True)
    existing = []
    if USER_REELS_LIBRARY.exists():
        for line in USER_REELS_LIBRARY.read_text(encoding="utf-8").splitlines():
            try:
                existing.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    reel_id = str(entry.get("릴스") or entry.get("instagram_media_id") or "")
    permalink = str(entry.get("링크") or "")
    replaced = False
    updated = []
    for item in existing:
        same_id = reel_id and reel_id == str(item.get("릴스") or item.get("instagram_media_id") or "")
        same_link = permalink and permalink == str(item.get("링크") or "")
        if same_id or same_link:
            merged = {**item, **entry}
            for preserved_key in ["analysis", "로컬영상", "촬영구도", "BGM", "BGM곡"]:
                if not entry.get(preserved_key) and item.get(preserved_key):
                    merged[preserved_key] = item[preserved_key]
            updated.append(merged)
            replaced = True
        else:
            updated.append(item)
    if not replaced:
        updated.append(entry)
    USER_REELS_LIBRARY.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in updated),
        encoding="utf-8",
    )


def meta_reel_to_library_entry(reel: dict, btype: str, username: str, store_id: str = "") -> dict:
    insights = normalize_insights(reel.get("insights"))
    score = performance_score(insights)
    caption = reel.get("caption") or ""
    return {
        "릴스": reel.get("id"),
        "instagram_media_id": reel.get("id"),
        "릴스명": make_reel_title({"caption": caption}, btype),
        "어떤 영상인지": shorten_text(first_caption_line(caption), 72),
        "원문": first_caption_line(caption),
        "캡션": caption,
        "링크": reel.get("permalink") or "",
        "로컬영상": "",
        "원격영상": reel.get("media_url") or reel.get("video_url") or "",
        "썸네일": reel.get("thumbnail_url") or "",
        "사용자": username,
        "store_id": store_id,
        "업종": btype,
        "조회수": int(insights["views"]),
        "좋아요": int(insights["likes"] or reel.get("like_count") or 0),
        "저장": int(insights["saved"]),
        "공유": int(insights["shares"]),
        "총점": score,
        "등급": "S" if score >= 85 else ("A" if score >= 70 else ("B" if score >= 50 else "C")),
        "길이(초)": 0,
        "촬영구도": "-",
        "BGM": "-",
        "BGM곡": "",
        "analysis": {},
        "insights": insights,
        "업로드": reel.get("timestamp") or datetime.now().isoformat(timespec="seconds"),
    }


def save_uploaded_reel(uploaded_file, suffix: str) -> Path:
    USER_REELS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = re.sub(r'[\\/:*?"<>|]', "_", Path(uploaded_file.name).stem)[:36] or "uploaded_reel"
    save_path = USER_REELS_DIR / f"{timestamp}_{safe_name}{suffix}"
    save_path.write_bytes(uploaded_file.getbuffer())
    return save_path


SAMPLE_REEL_IDEAS = {
    "카페": [
        ("소금빵 컷팅", "빵 결, 버터 향, 매장 위치가 바로 보이는 베이커리 릴스"),
        ("말차 수플레", "디저트 클로즈업과 저장 유도 문구가 강한 릴스"),
        ("신상 카페 투어", "처음 방문하는 손님이 동선을 이해하기 쉬운 소개형 릴스"),
        ("라떼아트 15초", "손기술과 분위기를 빠르게 보여주는 짧은 릴스"),
        ("브런치 메뉴 모음", "인기 메뉴 여러 개를 빠르게 비교해 보여주는 릴스"),
    ],
    "식당": [
        ("고기 굽는 첫 장면", "메뉴의 식감과 소리를 강조한 식당 릴스"),
        ("대표 메뉴 3가지", "방문 전 무엇을 먹을지 고르기 쉬운 메뉴 소개 릴스"),
        ("점심 특선 한 상", "가격과 구성을 한눈에 보여주는 실용형 릴스"),
    ],
    "뷰티": [
        ("네일 전후 비교", "시술 전후 차이가 바로 보이는 변신형 릴스"),
        ("피부 관리 과정", "관리 순서와 결과를 안정적으로 보여주는 릴스"),
    ],
    "패션": [
        ("출근룩 3가지", "상황별 코디를 비교하기 쉬운 패션 릴스"),
        ("신상 재킷 핏", "제품 실루엣과 착용감을 확인하기 쉬운 릴스"),
    ],
    "운동/헬스": [
        ("하체 운동 자세", "동작 전후와 주의점을 쉽게 보여주는 운동 릴스"),
        ("필라테스 교정", "변화가 명확해서 신뢰를 주는 교정형 릴스"),
    ],
}


DEFAULT_TREND_TRACKS = {
    "카페": [
        {
            "곡명": "Espresso",
            "아티스트": "Sabrina Carpenter",
            "편집법": "첫 잔 따르는 장면을 0.5초 컷으로 붙이고, 후렴 시작점에 메뉴 클로즈업을 맞춥니다.",
        },
        {
            "곡명": "APT.",
            "아티스트": "ROSÉ & Bruno Mars",
            "편집법": "문 열고 들어오는 장면, 메뉴판, 첫 입 장면을 박자마다 빠르게 전환합니다.",
        },
        {
            "곡명": "Golden",
            "아티스트": "HUNTR/X",
            "편집법": "디저트 단면이나 라떼아트처럼 결과물이 예쁜 장면을 상승하는 구간에 배치합니다.",
        },
        {
            "곡명": "ordinary",
            "아티스트": "Alex Warren",
            "편집법": "창가 좌석, 손님 동선, 따뜻한 조명처럼 감성 컷을 길게 보여줄 때 어울립니다.",
        },
    ],
    "식당": [
        {
            "곡명": "APT.",
            "아티스트": "ROSÉ & Bruno Mars",
            "편집법": "고기 굽는 소리, 음식 등장, 한입 먹는 장면을 박자에 맞춰 짧게 자릅니다.",
        },
        {
            "곡명": "Golden",
            "아티스트": "HUNTR/X",
            "편집법": "대표 메뉴가 완성되는 순간에 후렴을 맞추면 기대감이 살아납니다.",
        },
    ],
    "뷰티": [
        {
            "곡명": "Espresso",
            "아티스트": "Sabrina Carpenter",
            "편집법": "전후 비교 컷을 빠르게 교차하고, 결과 컷은 1초 이상 보여줍니다.",
        },
    ],
    "패션": [
        {
            "곡명": "APT.",
            "아티스트": "ROSÉ & Bruno Mars",
            "편집법": "착장 전환 타이밍을 박자에 맞추고, 전체 핏은 정면 고정샷으로 마무리합니다.",
        },
    ],
    "운동/헬스": [
        {
            "곡명": "Golden",
            "아티스트": "HUNTR/X",
            "편집법": "준비 자세, 핵심 동작, 완성 자세를 3단계로 끊어 보여줍니다.",
        },
    ],
}


CAMERA_GUIDES = {
    "탑뷰": {
        "한줄": "음식과 음료를 위에서 내려다보며 한 번에 보여주는 구도입니다.",
        "찍는법": "휴대폰을 테이블 위 40~60cm에 두고 카메라가 접시 중앙을 향하게 합니다.",
        "위치": "컵은 오른쪽 위, 대표 메뉴는 중앙, 손은 화면 아래쪽에서 들어오게 두면 안정적입니다.",
        "그림": "top",
    },
    "클로즈업": {
        "한줄": "크림, 빵 결, 얼음, 라떼아트처럼 질감이 중요한 장면을 크게 잡는 구도입니다.",
        "찍는법": "휴대폰을 메뉴에서 15~25cm 떨어뜨리고 초점을 메뉴 표면에 맞춥니다.",
        "위치": "메뉴가 화면의 70%를 차지하게 두고, 배경은 흐리게 정리합니다.",
        "그림": "close",
    },
    "팔로잉샷": {
        "한줄": "손님이 매장에 들어가거나 음료를 들고 이동하는 흐름을 따라가는 구도입니다.",
        "찍는법": "휴대폰을 가슴 높이에 두고 피사체 뒤나 옆에서 천천히 따라갑니다.",
        "위치": "피사체를 화면 중앙보다 살짝 앞쪽에 두고, 걷는 방향에 빈 공간을 남깁니다.",
        "그림": "follow",
    },
    "정면샷": {
        "한줄": "메뉴, 직원, 공간을 정면에서 안정적으로 보여주는 기본 구도입니다.",
        "찍는법": "휴대폰을 눈높이나 메뉴 높이에 맞추고 수평선을 맞춘 뒤 흔들림 없이 촬영합니다.",
        "위치": "보여주고 싶은 대상을 화면 중앙에 두고 좌우 여백을 비슷하게 맞춥니다.",
        "그림": "front",
    },
}


TREND_HASHTAGS = {
    "카페": ["#카페추천", "#카페스타그램", "#성수카페", "#신상카페", "#디저트맛집", "#소금빵맛집", "#카페투어", "#서울카페", "#릴스추천", "#저장각"],
    "식당": ["#맛집추천", "#서울맛집", "#성수맛집", "#점심추천", "#저녁메뉴", "#먹스타그램", "#맛집릴스", "#저장각"],
    "뷰티": ["#네일추천", "#피부관리", "#뷰티샵", "#전후비교", "#시술후기", "#뷰티릴스", "#저장각"],
    "패션": ["#데일리룩", "#출근룩", "#코디추천", "#패션릴스", "#신상추천", "#오늘뭐입지", "#저장각"],
    "운동/헬스": ["#운동루틴", "#헬스장", "#자세교정", "#필라테스", "#운동릴스", "#홈트", "#저장각"],
}


HOOK_GUIDES = [
    {
        "시간": "0~1초",
        "역할": "스크롤을 멈추는 첫 문장",
        "예시": "성수에서 이 메뉴 보이면 일단 저장하세요",
        "변형": "우리 동네/메뉴명/가격을 넣어 더 구체적으로 바꿉니다.",
    },
    {
        "시간": "1~3초",
        "역할": "왜 봐야 하는지 설명",
        "예시": "요즘 카페 릴스에서 조회수 잘 나오는 컷은 이 장면입니다",
        "변형": "조회수 대신 저장률, 예약, 재방문 같은 목표 단어로 바꿉니다.",
    },
    {
        "시간": "3~7초",
        "역할": "핵심 장면 2~3개 제시",
        "예시": "첫 컷은 메뉴 클로즈업, 두 번째는 매장 분위기, 마지막은 한입 컷",
        "변형": "내 가게의 대표 메뉴, 좌석, 직원 손동작으로 치환합니다.",
    },
    {
        "시간": "마지막 2초",
        "역할": "저장/방문 행동 유도",
        "예시": "이번 주말 갈 카페 찾는 중이면 저장",
        "변형": "예약 필요, 한정 메뉴, 위치 안내처럼 실제 행동으로 연결합니다.",
    },
]


def extract_store_keywords(description: str, btype: str) -> dict:
    if isinstance(description, dict):
        fallback = {
            "카페": {"menu": "대표 메뉴", "place": "우리 동네", "strength": "분위기"},
            "식당": {"menu": "대표 메뉴", "place": "우리 동네", "strength": "푸짐한 구성"},
            "뷰티": {"menu": "대표 시술", "place": "우리 동네", "strength": "전후 차이"},
            "패션": {"menu": "대표 상품", "place": "우리 동네", "strength": "핏"},
            "운동/헬스": {"menu": "대표 프로그램", "place": "우리 동네", "strength": "자세 교정"},
        }.get(btype, {"menu": "대표 상품", "place": "우리 동네", "strength": "차별점"})
        place = description.get("place") or fallback["place"]
        menu = description.get("menu") or fallback["menu"]
        strength = description.get("strength") or fallback["strength"]
        audience = description.get("audience") or "동네 손님"
        goal = description.get("goal") or "저장"
        text = " ".join([place, menu, strength, audience, goal])
        return {
            "menu": menu,
            "place": place,
            "strength": strength,
            "audience": audience,
            "goal": goal,
            "description": text,
        }

    text = re.sub(r"\s+", " ", description or "").strip()
    fallback = {
        "카페": {"menu": "대표 메뉴", "place": "우리 동네", "strength": "분위기"},
        "식당": {"menu": "대표 메뉴", "place": "우리 동네", "strength": "푸짐한 구성"},
        "뷰티": {"menu": "대표 시술", "place": "우리 동네", "strength": "전후 차이"},
        "패션": {"menu": "대표 상품", "place": "우리 동네", "strength": "핏"},
        "운동/헬스": {"menu": "대표 프로그램", "place": "우리 동네", "strength": "자세 교정"},
    }.get(btype, {"menu": "대표 상품", "place": "우리 동네", "strength": "차별점"})

    menu_candidates = [
        "소금빵", "라떼", "아메리카노", "디저트", "수플레", "말차", "브런치", "케이크",
        "파스타", "고기", "라멘", "국밥", "네일", "피부", "속눈썹", "재킷", "코디", "필라테스", "PT",
    ]
    strength_candidates = {
        "조용": "조용한 분위기",
        "감성": "감성적인 공간",
        "신상": "새로움",
        "예약": "예약하고 가야 하는 희소성",
        "가성비": "가성비",
        "수제": "직접 만드는 과정",
        "전후": "전후 차이",
        "뷰": "공간의 뷰",
        "친절": "친절한 응대",
    }

    menu = next((word for word in menu_candidates if word in text), fallback["menu"])
    strength = next((label for key, label in strength_candidates.items() if key in text), fallback["strength"])

    place_match = re.search(r"([가-힣A-Za-z0-9]+(?:동|역|구|시|읍|면|리|로|길))", text)
    place = place_match.group(1) if place_match else fallback["place"]

    return {"menu": menu, "place": place, "strength": strength, "audience": "동네 손님", "goal": "저장", "description": text}


def build_personalized_guide(description: str, btype: str, primary_camera: str, tracks: list[dict], hashtags: list[str]) -> dict:
    keywords = extract_store_keywords(description, btype)
    menu = keywords["menu"]
    place = keywords["place"]
    strength = keywords["strength"]
    audience = keywords.get("audience", "동네 손님")
    goal = keywords.get("goal", "저장")
    track = tracks[0] if tracks else {"곡명": "인기 음원", "편집법": "박자에 맞춰 핵심 장면을 전환합니다."}

    if any(word in strength for word in ["조용", "감성", "뷰", "분위기"]):
        track = next((item for item in tracks if item["곡명"].lower() in {"ordinary", "golden"}), track)
        track_reason = "공간 분위기와 체류감을 보여줘야 해서 너무 빠른 곡보다 감성적인 곡이 어울립니다."
    elif menu in {"소금빵", "라떼", "디저트", "수플레", "말차", "브런치", "케이크"}:
        track = next((item for item in tracks if item["곡명"].lower() in {"espresso", "apt."}), track)
        track_reason = "메뉴 클로즈업과 손동작 컷을 박자에 맞춰 빠르게 보여주기 좋습니다."
    else:
        track_reason = "대표 장면을 짧게 반복해서 보여주는 편집과 잘 맞습니다."

    if any(word in strength for word in ["공간", "조용", "감성", "뷰"]):
        recommended_camera = "정면샷"
        camera_reason = "메뉴만 크게 보여주기보다 매장 분위기와 좌석 느낌까지 같이 보여주는 편이 좋습니다."
    elif menu in {"소금빵", "라떼", "디저트", "수플레", "말차", "브런치", "케이크", "고기", "파스타", "라멘", "국밥"}:
        recommended_camera = "클로즈업"
        camera_reason = "대표 메뉴의 질감과 먹음직스러운 순간이 먼저 보여야 스크롤을 멈추기 쉽습니다."
    elif strength in {"전후 차이", "핏", "자세 교정"}:
        recommended_camera = "정면샷"
        camera_reason = "변화나 핏, 자세는 정면에서 비교해야 초보자도 차이를 바로 이해합니다."
    else:
        recommended_camera = primary_camera
        camera_reason = "현재 상위 릴스에서 가장 자주 보이는 구도라 우선 적용하기 좋습니다."

    hooks = [
        f"{place}에서 {menu} 찾는 중이면 이 장면부터 보세요",
        f"{menu}는 가까이서 찍어야 {goal}됩니다",
        f"{audience}이 바로 이해하는 {btype} 릴스 구성",
        f"{strength}이 보이게 찍는 {menu} 15초 컷",
    ]

    scenes = [
        f"0~1초: {menu}가 가장 맛있거나 예쁘게 보이는 장면을 {recommended_camera}로 먼저 보여줍니다.",
        f"1~3초: '{place} {menu}'가 보이도록 짧은 자막을 올립니다.",
        f"3~7초: 메뉴 클로즈업, 공간 한 컷, 손동작 한 컷을 빠르게 이어 붙입니다.",
        f"7~12초: {strength}이 드러나는 장면을 한 번 더 보여줍니다.",
        f"마지막 2초: {goal} 행동을 한 번만 분명하게 유도합니다.",
    ]

    captions = [
        f"{place}에서 {menu} 찾는다면 {goal}해두세요.",
        f"첫 방문이면 이 순서로 주문하면 실패 확률이 낮아요.",
        f"{strength} 좋아하는 {audience}이면 이번 주 안에 들러보세요.",
    ]

    selected_hashtags = hashtags[:7] + [f"#{place}", f"#{menu}"]
    return {
        "keywords": keywords,
        "hooks": hooks,
        "scenes": scenes,
        "captions": captions,
        "track": track,
        "track_reason": track_reason,
        "camera": recommended_camera,
        "camera_reason": camera_reason,
        "hashtags": list(dict.fromkeys(selected_hashtags)),
    }


def get_reel_track_name(row: pd.Series) -> str:
    for key in ["BGM곡", "음원", "음악", "music_title", "song_name", "track_name"]:
        value = row.get(key)
        if value and str(value).strip() and str(value).strip() != "-":
            return str(value).strip()
    return ""


def trend_tracks_for(btype: str, source_df: pd.DataFrame) -> list[dict]:
    actual_tracks = []
    if not source_df.empty:
        for _, row in source_df.iterrows():
            track_name = get_reel_track_name(row)
            if track_name and track_name not in actual_tracks:
                actual_tracks.append(track_name)

    if actual_tracks:
        return [
            {
                "곡명": track,
                "아티스트": "수집 릴스 기반",
                "편집법": "해당 음원의 박자가 바뀌는 지점에 메뉴 등장, 컷 전환, 결과 장면을 맞춰 편집합니다.",
            }
            for track in actual_tracks[:5]
        ]
    return DEFAULT_TREND_TRACKS.get(btype, DEFAULT_TREND_TRACKS["카페"])


def top_camera_guides(source_df: pd.DataFrame) -> list[tuple[str, int, dict]]:
    counts = source_df["촬영구도"].value_counts()
    guides = []
    for camera_name, count in counts.items():
        guide = CAMERA_GUIDES.get(camera_name)
        if guide:
            guides.append((camera_name, int(count), guide))
    if guides:
        return guides[:4]
    return [(name, 0, guide) for name, guide in CAMERA_GUIDES.items()]


def get_guide_source_reels(source_df: pd.DataFrame, limit: int = 3) -> pd.DataFrame:
    if source_df.empty:
        return source_df
    real_sources = source_df[source_df["출처"].isin(["실제 수집", "직접 추가"])].copy()
    if not real_sources.empty:
        return real_sources.head(limit)
    return source_df.head(limit)


def camera_evidence_text(source_df: pd.DataFrame, camera_name: str) -> str:
    if source_df.empty:
        return "분석된 릴스가 쌓이면 해당 구도를 사용한 실제 사례가 여기에 표시됩니다."

    matched = source_df[source_df["촬영구도"].astype(str).str.contains(camera_name, na=False)]
    if matched.empty:
        matched = source_df.head(2)
    names = [str(row.get("릴스명") or row.get("릴스")) for _, row in matched.head(2).iterrows()]
    return "근거 릴스: " + ", ".join(names)


def storyboard_evidence_text(source_df: pd.DataFrame) -> str:
    source_reels = get_guide_source_reels(source_df, 3)
    if source_reels.empty:
        return "상위 릴스의 구도, 길이, 점수 패턴이 쌓이면 스토리보드 근거가 더 구체화됩니다."
    names = [f"{row['릴스명']}({float(row['총점']):.1f}점)" for _, row in source_reels.iterrows()]
    return "스토리보드는 " + ", ".join(names) + "의 초반 구도와 저장 유도 흐름을 반영했습니다."


def render_shot_diagram(diagram_type: str) -> str:
    if diagram_type == "top":
        inner = """
          <div class="cup"></div><div class="plate"></div><div class="hand"></div>
          <div class="shot-label label-side">컵</div>
          <div class="shot-label label-main">메뉴</div>
          <div class="shot-label label-bottom">손</div>
        """
        caption = "위에서 내려다본 화면 구성"
    elif diagram_type == "close":
        inner = """
          <div class="subject"></div>
          <div class="shot-label label-center">메뉴 크게</div>
        """
        caption = "메뉴가 화면 대부분을 차지"
    elif diagram_type == "follow":
        inner = """
          <div class="path-line"></div><div class="face"></div><div class="subject"></div>
          <div class="shot-label label-top">사람</div>
          <div class="shot-label label-path">이동 방향</div>
        """
        caption = "피사체를 따라가며 여백을 남김"
    else:
        inner = """
          <div class="face"></div><div class="counter"></div>
          <div class="shot-label label-top">직원/메뉴</div>
          <div class="shot-label label-bottom">테이블</div>
        """
        caption = "정면에서 수평을 맞춘 화면"

    return f"""
    <div class="shot-card">
      <div class="phone-frame">{inner}</div>
      <div style="text-align:center; color: var(--muted); font-size: 0.875rem;">{caption}</div>
    </div>
    """


def build_storyboard_steps(
    btype: str,
    primary_camera: str,
    personalized: dict | None,
    analysis: dict | None = None,
    project: dict | None = None,
) -> list[dict]:
    if project:
        return build_project_storyboard(project, btype, primary_camera, analysis)
    if personalized:
        keywords = personalized["keywords"]
        menu = keywords["menu"]
        place = keywords["place"]
        strength = keywords["strength"]
        goal = keywords.get("goal", "저장")
        hook = personalized["hooks"][0]
        caption = personalized["captions"][0]
        camera = personalized.get("camera", primary_camera)
    else:
        menu = "대표 메뉴"
        place = "우리 동네"
        strength = "가게 강점"
        goal = "저장"
        hook = f"{place}에서 {menu} 찾는 중이면 이 장면부터 보세요"
        caption = f"{place}에서 {menu} 찾는다면 {goal}해두세요."
        camera = primary_camera

    steps = [
        {
            "title": "1. 첫 장면: 스크롤 멈추기",
            "hook": "0~1초 · 스크롤을 멈추는 첫 문장",
            "scene": "scene-hero",
            "subtitle": hook,
            "subtitle_class": "subtitle-top subtitle-accent",
            "shoot": f"{camera}로 {menu}가 가장 맛있거나 예쁜 순간을 화면 중앙에 둡니다.",
            "text": "자막은 화면 상단 10~15% 위치, 파란 배경+흰 글씨로 짧게 넣습니다.",
            "edit": "0.7~1.0초만 보여주고 바로 다음 컷으로 넘깁니다.",
        },
        {
            "title": "2. 디테일 컷: 저장할 이유 만들기",
            "hook": "1~3초 · 왜 봐야 하는지 설명",
            "scene": "scene-close",
            "subtitle": f"{menu} 디테일은 가까이서",
            "subtitle_class": "subtitle-bottom",
            "shoot": f"휴대폰을 {menu}에 가까이 대고 질감, 김, 단면, 색감을 크게 잡습니다.",
            "text": "자막은 하단 15% 위치, 검정 반투명 배경+흰 글씨가 가장 안전합니다.",
            "edit": "BGM 박자에 맞춰 0.5초 컷 2~3개로 끊습니다.",
        },
        {
            "title": "3. 공간/맥락 컷: 어디인지 이해시키기",
            "hook": "3~7초 · 핵심 장면 2~3개 제시",
            "scene": "scene-space",
            "subtitle": f"{place} · {strength}",
            "subtitle_class": "subtitle-mid subtitle-light",
            "shoot": f"매장 입구, 좌석, 메뉴가 놓인 테이블 중 {strength}이 보이는 장면을 찍습니다.",
            "text": "자막은 중앙보다 살짝 아래, 흰 배경+진한 글씨로 장소와 강점을 보여줍니다.",
            "edit": "너무 길게 끌지 말고 1.0~1.5초만 넣어 정보 컷으로 사용합니다.",
        },
        {
            "title": "4. 손동작 컷: 사람이 있는 느낌 넣기",
            "hook": "7~12초 · 실제 사용/경험 장면",
            "scene": "scene-hand",
            "subtitle": "집는 장면 / 따르는 장면 / 한입 장면",
            "subtitle_class": "subtitle-bottom",
            "shoot": "손이 화면 아래에서 들어오게 찍으면 초보자가 봐도 장면의 목적이 바로 보입니다.",
            "text": "자막은 아주 짧게, 동작을 가리지 않도록 하단 바깥쪽에 둡니다.",
            "edit": "손동작이 시작되는 순간부터 끝나는 순간까지만 남깁니다.",
        },
        {
            "title": f"5. 마지막 컷: {goal} 유도",
            "hook": "마지막 2초 · 저장/방문 행동 유도",
            "scene": "scene-cta",
            "subtitle": caption,
            "subtitle_class": "subtitle-mid subtitle-accent",
            "shoot": "대표 장면을 다시 보여주거나 메뉴+매장명이 같이 보이는 안정적인 컷을 씁니다.",
            "text": f"문구는 화면 중앙에 크게. 행동은 `{goal}` 하나만 말합니다.",
            "edit": "마지막 1.5~2초를 유지하고, 캡션 첫 줄에도 같은 문구를 넣습니다.",
        },
    ]
    analysis = analysis or {}
    actions = analysis.get("priority_actions") or []
    risks = [item for item in analysis.get("timeline_diagnostics", []) if item.get("kind") == "risk"]
    for index, action in enumerate(actions[:3]):
        steps[min(index, len(steps) - 1)]["edit"] += f" 이전 영상 분석 반영: {action}"
    if risks:
        steps[0]["analysis_note"] = f"이전 영상 {float(risks[0].get('timestamp_seconds', 0)):.1f}초 위험 구간을 보완하는 구성입니다."
    return steps


def render_storyboard_card(step: dict) -> str:
    title = html.escape(str(step.get("title", "")))
    hook = html.escape(str(step.get("hook", "")))
    scene = html.escape(str(step.get("scene", "scene-hero")), quote=True)
    scene_style = html.escape(str(step.get("scene_style", "")), quote=True)
    scene_label = html.escape(str(step.get("scene_label", "피사체")))
    subtitle_class = html.escape(str(step.get("subtitle_class", "subtitle-top")), quote=True)
    subtitle_style = html.escape(str(step.get("subtitle_style", "")), quote=True)
    subtitle = html.escape(str(step.get("subtitle", "")))
    focus_style = html.escape(str(step.get("focus_style", "")), quote=True)
    focus_label = html.escape(str(step.get("focus_label", "물품 중심")))
    shoot = html.escape(str(step.get("shoot", "")))
    text_note = html.escape(str(step.get("text", "")))
    edit = html.escape(str(step.get("edit", "")))
    analysis_note = html.escape(str(step.get("analysis_note", "")))
    geometry_note = html.escape(str(step.get("geometry_note", "")))
    motion_type = str(step.get("motion_type") or "hold")
    has_motion = motion_type in {"zoom_in", "zoom_out", "pan"}
    motion_class = " story-motion" if has_motion else ""
    phone_class = " has-depth" if motion_type in {"zoom_in", "zoom_out"} else ""
    motion_labels = {"zoom_in": "↗ 확대 반복", "zoom_out": "↙ 축소 반복", "pan": "→ 이동 반복", "hold": "고정"}
    motion_badge = html.escape(motion_labels.get(motion_type, "고정"))
    motion_note = html.escape(str(step.get("motion_note", "")))
    motion_css = ""
    if has_motion:
        def frame(box: dict) -> str:
            return (
                f"left:{float(box.get('x', 0)):.1f}%;top:{float(box.get('y', 0)):.1f}%;"
                f"width:{float(box.get('width', 1)):.1f}%;height:{float(box.get('height', 1)):.1f}%;"
            )

        scene_start = step.get("motion_start_bbox") or {}
        scene_end = step.get("motion_end_bbox") or scene_start
        focus_start = step.get("focus_motion_start_bbox") or {}
        focus_end = step.get("focus_motion_end_bbox") or focus_start
        token_source = json.dumps([title, scene_start, scene_end], ensure_ascii=False, sort_keys=True)
        token = hashlib.sha256(token_source.encode("utf-8")).hexdigest()[:10]
        scene_animation = f"storyScene{token}"
        focus_animation = f"storyFocus{token}"
        scene_style += f"animation:{scene_animation} 2.8s cubic-bezier(.45,0,.2,1) infinite;"
        focus_style += f"animation:{focus_animation} 2.8s cubic-bezier(.45,0,.2,1) infinite;"
        motion_css = (
            f"<style>@keyframes {scene_animation}{{0%,12%,100%{{{frame(scene_start)}}}62%,88%{{{frame(scene_end)}}}}}"
            f"@keyframes {focus_animation}{{0%,12%,100%{{{frame(focus_start)}}}62%,88%{{{frame(focus_end)}}}}}</style>"
        )
    return f"""
    {motion_css}
    <div class="storyboard-card">
      <div class="storyboard-title">{title}</div>
      <p class="story-note"><strong>후킹 역할:</strong> {hook}</p>
      <div class="story-phone{phone_class}">
        <div class="story-motion-badge">{motion_badge}</div>
        <div class="story-scene {scene}{motion_class}" style="{scene_style}"><span class="story-scene-label">{scene_label}</span></div>
        <div class="story-focus-point{motion_class}" style="{focus_style}">{focus_label}</div>
        <div class="story-subtitle {subtitle_class}" style="{subtitle_style}">{subtitle}</div>
      </div>
      {f'<p class="story-note"><strong>원근·움직임:</strong> {motion_note} · 그림이 실제 좌표 사이를 반복합니다.</p>' if motion_note else ''}
      {f'<p class="story-note"><strong>구도 근거:</strong> {geometry_note}</p>' if geometry_note else ''}
      <p class="story-note"><strong>촬영:</strong> {shoot}</p>
      <p class="story-note"><strong>문구 위치/스타일:</strong> {text_note}</p>
      <p class="story-note"><strong>편집:</strong> {edit}</p>
      {f'<p class="story-note"><strong>분석 반영:</strong> {analysis_note}</p>' if analysis_note else ''}
    </div>
    """


def production_plan_to_storyboard(plan: dict) -> list[dict]:
    scene_map = {"클로즈업": "scene-close", "탑뷰": "scene-hero", "팔로잉샷": "scene-hand", "정면샷": "scene-space"}
    steps = []
    for shot in plan.get("shots") or []:
        camera = shot.get("camera", "정면샷")
        steps.append({
            "title": f"{shot.get('index', len(steps) + 1)}. {shot.get('shot', '촬영 장면')}",
            "hook": f"{shot.get('start_seconds', 0):.1f}~{shot.get('end_seconds', 0):.1f}초 · {shot.get('fixes_issue', '핵심 메시지 전달')}",
            "scene": scene_map.get(camera, "scene-space"),
            "subtitle": shot.get("on_screen_text") or plan.get("hook") or "",
            "subtitle_class": "subtitle-top subtitle-accent" if not steps else "subtitle-bottom",
            "shoot": f"{camera}: {shot.get('direction', '')}",
            "text": f"화면 문구: {shot.get('on_screen_text', '-')} · 내레이션: {shot.get('voiceover', '-')}",
            "edit": shot.get("edit") or "장면 목적에 맞춰 짧게 편집합니다.",
            "analysis_note": shot.get("fixes_issue") or "",
        })
    return steps


def render_motion_storyboard(storyboard_steps: list[dict]) -> str:
    captions = [step["subtitle"] for step in storyboard_steps]
    safe_captions = captions + [""] * max(0, 5 - len(captions))
    return f"""
    <div class="motion-guide">
      <div class="storyboard-title">움직임 미리보기 · 15초 반복</div>
      <div class="motion-phone">
        <div class="motion-scene">
          <div class="motion-step">1</div>
          <div class="motion-object motion-plate"></div>
          <div class="motion-caption top">{safe_captions[0]}</div>
        </div>
        <div class="motion-scene">
          <div class="motion-step">2</div>
          <div class="motion-object motion-close"></div>
          <div class="motion-caption bottom">{safe_captions[1]}</div>
        </div>
        <div class="motion-scene">
          <div class="motion-step">3</div>
          <div class="motion-object motion-space"></div>
          <div class="motion-caption mid">{safe_captions[2]}</div>
        </div>
        <div class="motion-scene">
          <div class="motion-step">4</div>
          <div class="motion-object motion-hand"></div>
          <div class="motion-caption bottom">{safe_captions[3]}</div>
        </div>
        <div class="motion-scene">
          <div class="motion-step">5</div>
          <div class="motion-object motion-cta"></div>
          <div class="motion-caption mid">{safe_captions[4]}</div>
        </div>
      </div>
      <p class="story-note"><strong>보는 법:</strong> 파란/초록 박스는 메뉴나 손이 이동하는 위치, 자막 박스는 실제 화면에 넣을 문구 위치입니다.</p>
      <p class="story-note"><strong>촬영 감각:</strong> 1번은 중앙으로 맞추기, 2번은 가까이 당기기, 3번은 좌우로 훑기, 4번은 손동작 따라가기, 5번은 문구를 크게 유지하기입니다.</p>
    </div>
    """


def get_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def get_mobile_coach_url() -> str:
    configured = get_env("MOBILE_COACH_BASE_URL")
    if configured:
        return configured.rstrip("/") + "/mobile-coach.html"
    return f"http://{get_lan_ip()}:8502/mobile-coach.html"


def get_app_return_url() -> str:
    configured = get_env("APP_BASE_URL")
    if configured:
        return configured.rstrip("/") + "/?view=analysis"
    return f"http://{get_lan_ip()}:8501/?view=analysis"


MOBILE_COACH_SERVER = (
    {"running": True, "external": True}
    if get_env("MOBILE_COACH_BASE_URL")
    else ensure_mobile_coach_server(Path(__file__).resolve().parent / "mobile_coach")
)


# ── 목업 데이터 ───────────────────────────────
@st.cache_data
def get_mock_reels(btype: str) -> pd.DataFrame:
    random.seed(42)
    rows = load_download_log_reels(btype)
    rows.extend(load_user_reels(btype))
    ideas = SAMPLE_REEL_IDEAS.get(btype, SAMPLE_REEL_IDEAS["카페"])
    for i in range(max(0, 20 - len(rows))):
        v = random.randint(3000, 150000)
        l = int(v * random.uniform(0.02, 0.08))
        s = int(v * random.uniform(0.01, 0.05))
        sh = int(v * random.uniform(0.005, 0.02))
        norm = min((v * 0.2 + l * 0.3 + (s + sh) * 0.5) / 35000 * 100, 100)
        display_score = round(min(norm, 84.0), 1)
        tier = "S" if display_score >= 80 else ("A" if display_score >= 60 else ("B" if display_score >= 40 else "C"))
        title, context = ideas[i % len(ideas)]
        rows.append({
            "릴스": f"demo_{i+1:03d}",
            "릴스명": title,
            "어떤 영상인지": context,
            "원문": title,
            "캡션": context,
            "링크": "https://www.instagram.com/reels/",
            "로컬영상": "",
            "사용자": "",
            "출처": "예시",
            "업종": btype, "조회수": v,
            "좋아요": l, "저장": s, "공유": sh, "총점": display_score, "등급": tier,
            "길이(초)": random.choice([15, 20, 30, 45, 60]),
            "촬영구도": random.choice(["탑뷰", "클로즈업", "팔로잉샷", "정면샷"]),
            "BGM": random.choice(["신나는", "감성적", "조용한"]),
            "BGM곡": "",
            "analysis": {},
            "insights": {},
            "업로드": datetime.now() - timedelta(days=random.randint(1, 60)),
        })
    return pd.DataFrame(rows).sort_values("총점", ascending=False).reset_index(drop=True)


# ── 사이드바 ──────────────────────────────────
MENU_OPTIONS = ["Home", "Radar", "Studio", "Insights", "Playbook", "Settings"]
MAX_UPLOAD_MB = 200
PLOT_CONFIG = {"displaylogo": False, "responsive": True}
TIER_COLORS = {"S": "#007f94", "A": "#16845b", "B": "#5f6f76", "C": "#c13b32"}

if "store_profile" not in st.session_state:
    st.session_state["store_profile"] = load_store_profile()

initial_query = st.query_params
if initial_query.get("view", "") == "analysis":
    st.session_state["active_menu"] = "Studio"
    if initial_query.get("project", ""):
        st.session_state["active_project_id"] = initial_query.get("project", "")
    st.query_params.clear()

app_layout = appearance_controls()

menu = render_navigation(app_layout)

# Keep the business selection when widgets move between web and app layouts.
btype = st.session_state.get("business_type", "카페")
if not app_layout or menu == "Settings":
    with (st.container() if app_layout else st.sidebar):
        business_types = ["카페", "식당", "뷰티", "패션", "운동/헬스", "기타"]
        btype = st.selectbox("내 업종", business_types, index=business_types.index(btype))
        st.session_state["business_type"] = btype
        if AUTH_USER_ID:
            st.caption((st.session_state.get("app_auth") or {}).get("email", AUTH_USER_ID))
            if st.button("로그아웃", use_container_width=True):
                st.session_state.pop("app_auth", None)
                configure_auth_session()
                st.rerun()

df = get_mock_reels(btype)


def page_header(title: str, description: str = ""):
    page_name = menu.split(" ", 1)[1] if " " in menu else menu
    clean_title = re.sub(r"^[^\w가-힣]+", "", title).strip()
    st.markdown(
        f"""
        <div class="page-heading">
          <div class="page-kicker">WORKSPACE / {page_name}</div>
          <h1>{clean_title}</h1>
          {f'<p>{description}</p>' if description else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )


def show_analysis_result(analysis: dict, report_text: str, report_path: Path) -> None:
    st.success("분석 완료")
    r1, r2, r3 = st.columns(3)
    r1.metric("사용 프레임", f"{analysis.get('frame_count', 0)}장")
    r2.metric("자막 위치", analysis.get("subtitle_position", "-"))
    r3.metric("색감", analysis.get("color_tone", "-"))

    st.divider()
    a1, a2 = st.columns(2)
    with a1:
        st.markdown("**📷 촬영 분석**")
        st.markdown(
            "\n".join([
                f"- 구도: {', '.join(analysis.get('camera_angles', [])) or '-'}",
                f"- 컷 속도: {analysis.get('cut_speed', '-')}",
                f"- 첫 장면: {analysis.get('hook_text', '-')}",
            ])
        )
    with a2:
        st.markdown("**🎵 오디오/텍스트**")
        st.markdown(
            "\n".join([
                f"- BGM: {analysis.get('bgm_mood', '-')}",
                f"- 캡션 후킹: {', '.join(analysis.get('caption_hooks', [])) or '-'}",
            ])
        )

    st.info(analysis.get("analysis_summary", "분석 요약을 생성하지 못했습니다."))

    scores = analysis.get("category_scores") or {}
    if any(float(value or 0) > 0 for value in scores.values()):
        st.markdown("**게시 전 AI 예상 점수**")
        score_cols = st.columns(6)
        labels = [("종합", analysis.get("overall_score", 0)), ("훅", scores.get("hook", 0)),
                  ("속도", scores.get("pacing", 0)), ("오디오", scores.get("audio", 0)),
                  ("화면", scores.get("visual", 0)), ("참여", scores.get("engagement", 0))]
        for col, (label, value) in zip(score_cols, labels):
            col.metric(label, f"{float(value or 0):.0f}")
        st.caption("이 점수와 유지율은 샘플 프레임을 바탕으로 만든 AI 예상치이며 실제 Instagram 통계가 아닙니다.")

    timeline = analysis.get("timeline_diagnostics") or []
    timeline_signals = analysis.get("timeline_signals") or []
    if timeline or timeline_signals:
        st.markdown("**구간별 진단**")
        if timeline_signals:
            timeline_df = pd.DataFrame(timeline_signals)
            fig = px.line(
                timeline_df,
                x="timestamp_seconds",
                y="predicted_retention",
                markers=False,
                labels={"timestamp_seconds": "영상 시각(초)", "predicted_retention": "휴리스틱 예상 유지율"},
                color_discrete_sequence=["#09cbea"],
            )
            fig.update_yaxes(range=[0, 100])
            fig.update_layout(height=260, margin=dict(l=0, r=0, t=10, b=0),
                              plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, use_container_width=True, config=PLOT_CONFIG)
        for item in timeline:
            marker = "강점" if item.get("kind") == "strength" else "수정 후보"
            with st.expander(f"{float(item.get('timestamp_seconds', 0)):.1f}초 · {marker} · {item.get('title', '')}"):
                st.markdown(f"**근거**: {item.get('reason', '-')}")
                st.markdown(f"**수정안**: {item.get('action', '-')}")
                st.caption(
                    f"휴리스틱 예상 유지율 {float(item.get('predicted_retention', 0)):.0f}% · "
                    f"신뢰도 {item.get('confidence', 'low')} · 근거 {item.get('evidence', 'ai_semantic')}"
                )
        st.caption(
            "그래프는 전체 영상의 화면 변화량과 오디오 에너지로 계산한 편집 위험 지표입니다. "
            "실제 Instagram 시청자 유지율은 게시 후 실측 데이터로 별도 검증합니다."
        )

    actions = analysis.get("priority_actions") or []
    if actions:
        st.markdown("**먼저 고칠 3가지**")
        for index, action in enumerate(actions, start=1):
            st.markdown(f"{index}. {action}")
    st.download_button(
        "보고서 다운로드",
        data=report_text,
        file_name=report_path.name,
        mime="text/markdown",
        use_container_width=True,
    )
    st.caption(f"저장 위치: {report_path}")


def write_analysis_report(analysis: dict, stem: str) -> tuple[str, Path]:
    report_text = format_report(analysis)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    safe_stem = re.sub(r'[\\/:*?"<>|]', "_", stem)[:48] or "reel"
    report_path = reports_dir / f"{timestamp}_{safe_stem}_report.md"
    report_path.write_text(report_text, encoding="utf-8")
    return report_text, report_path


def go_to_menu(target: str) -> None:
    st.session_state["nav_target"] = target
    st.rerun()


def attach_analysis_to_active_project(analysis: dict) -> dict | None:
    project_id = st.session_state.get("active_project_id")
    if not project_id:
        return None
    return update_project(
        project_id,
        {
            "analysis": analysis,
            "edit_notes": analysis.get("priority_actions") or [],
            "stage": "review",
        },
        CONTENT_PROJECTS_PATH,
    )


# The product workspace is intentionally project-first. The legacy UI below stays
# in place for backwards compatibility while this entry point owns user workflows.
workspace_context = {
    "projects_path": CONTENT_PROJECTS_PATH,
    "business_type": btype,
    "audio_registry": AUDIO_RIGHTS_REGISTRY,
    "uploads_dir": USER_REELS_DIR / "uploads",
    "guides_dir": USER_REELS_DIR / "guides",
    "performance_history_path": USER_REELS_DIR / "performance_history.jsonl",
    "playbook_path": USER_REELS_DIR / "playbook_patterns.json",
    "workspace_settings_path": USER_REELS_DIR / "workspace_settings.json",
    "study_path": USER_REELS_DIR / "radar_study.json",
    "mobile_coach_url": get_mobile_coach_url(),
    "mobile_coach_server": MOBILE_COACH_SERVER,
    "app_return_url": get_app_return_url(),
    "analyze_file": analyze_reel_from_file,
    "analyze_thumbnail": analyze_reel_from_thumbnail,
    "analyze_sequence_url": analyze_reel_sequence_from_url,
    "can_analyze_visual": has_env("GEMINI_API_KEY") or has_env("GOOGLE_API_KEY"),
    "can_generate_image": has_env("BFL_API_KEY"),
    "can_generate_voice": has_env("ELEVENLABS_API_KEY") and has_env("ELEVENLABS_VOICE_ID"),
    "build_storyboard_steps": build_storyboard_steps,
    "render_storyboard_card": render_storyboard_card,
    "load_user_reels": load_user_reels,
    "list_jobs": lambda: list_jobs(limit=100, owner_id=JOB_OWNER_ID, path=JOB_DB_PATH),
    "can_collect": has_env("APIFY_TOKEN"),
    "collect": collect_top_reels,
    "collect_url": get_reel_from_url,
    "load_previous": lambda query: load_previous_snapshot(query, base_dir=MARKET_SNAPSHOT_DIR),
    "build_snapshot": build_market_snapshot,
    "compare_snapshots": compare_snapshots,
    "save_snapshot": lambda snapshot: save_snapshot(snapshot, base_dir=MARKET_SNAPSHOT_DIR),
    "service_status": [
        ("Instagram / Meta", bool(get_env("META_ACCESS_TOKEN") or st.session_state.get("meta_access_token"))),
        ("Market signals", has_env("APIFY_TOKEN")),
        ("AI analysis", has_env("GEMINI_API_KEY") or has_env("GOOGLE_API_KEY")),
    ],
    "meta_oauth_ready": all(has_env(name) for name in ["META_APP_ID", "META_APP_SECRET", "META_REDIRECT_URI"]),
    "meta_token_present": bool(get_env("META_ACCESS_TOKEN") or st.session_state.get("meta_access_token")),
    "build_oauth_url": build_oauth_url,
    "exchange_oauth": exchange_authorization_code,
    "save_meta_token": lambda token, payload: (
        save_encrypted_token(
            token,
            get_env("META_TOKEN_ENCRYPTION_KEY"),
            META_TOKEN_VAULT,
            {"expires_in": payload.get("expires_in"), "auth_user_id": AUTH_USER_ID, "business_type": btype},
        ) if get_env("META_TOKEN_ENCRYPTION_KEY") else None
    ),
    "is_admin": get_env_bool("ADMIN_MODE", False),
}
render_workspace(menu, workspace_context)
st.stop()


# ══════════════════════════════════════
# 🏠 메인
# ══════════════════════════════════════
if menu == "Home":
    content_projects = list_projects(CONTENT_PROJECTS_PATH)
    stage_counts = pipeline_counts(content_projects)
    active_project = next((item for item in content_projects if item.get("stage") != "posted"), None)
    st.markdown(
        f"""
        <div class="workspace-header">
          <div>
            <div class="workspace-kicker">HOME / THIS WEEK</div>
            <h1>{'이어서 만들 릴스가 있습니다.' if active_project else '다음 릴스를 시작하세요.'}</h1>
            <p>{next_action(active_project) if active_project else '잘된 소재를 찾거나, 떠오른 아이디어를 바로 프로젝트로 만드세요.'}</p>
          </div>
          <div class="workspace-pulse">
            <span>{btype} CONTENT PIPELINE</span>
            <strong>{len(content_projects)} PROJECTS</strong>
            <span>{stage_counts['posted']} posted · {sum(stage_counts[key] for key in PROJECT_STAGES[:-1])} in progress</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    pipeline_cols = st.columns(5)
    for column, stage in zip(pipeline_cols, PROJECT_STAGES):
        column.metric(STAGE_LABELS[stage], stage_counts[stage])

    action_col, start_col = st.columns([1.7, 1])
    with action_col:
        st.subheader("Next action")
        if active_project:
            st.markdown(f"### {active_project['title']}")
            st.caption(f"{STAGE_LABELS.get(active_project.get('stage'), 'Idea')} · 마지막 수정 {active_project.get('updated_at', '-')}")
            st.write(next_action(active_project))
            if st.button("Open in Studio", type="primary", use_container_width=True):
                st.session_state["active_project_id"] = active_project["id"]
                go_to_menu("Studio")
        else:
            st.info("진행 중인 프로젝트가 없습니다. 새 프로젝트를 만들거나 Radar에서 소재를 저장하세요.")
            if st.button("Explore Radar", type="primary", use_container_width=True):
                go_to_menu("Radar")

    with start_col:
        st.subheader("New project")
        with st.form("home_new_project"):
            project_title = st.text_input("Project title", placeholder="예: 신메뉴 크림라떼 15초")
            project_concept = st.text_area("Starting idea", placeholder="보여주고 싶은 메뉴나 손님의 문제", height=90)
            submitted = st.form_submit_button("Create project", use_container_width=True)
        if submitted:
            project = create_project(
                project_title or project_concept,
                CONTENT_PROJECTS_PATH,
                business_type=btype,
                concept=project_concept,
            )
            st.session_state["active_project_id"] = project["id"]
            go_to_menu("Studio")

    if content_projects:
        st.divider()
        st.subheader("Recent projects")
        project_rows = [{
            "Project": item.get("title"),
            "Stage": STAGE_LABELS.get(item.get("stage"), item.get("stage")),
            "Next": next_action(item),
            "Updated": item.get("updated_at"),
        } for item in content_projects[:8]]
        st.dataframe(pd.DataFrame(project_rows), use_container_width=True, hide_index=True)


# ══════════════════════════════════════
# 📊 대시보드
# ══════════════════════════════════════
elif menu == "Insights":
    real_dashboard_df = df[df["출처"] != "예시"].copy()
    dashboard_df = real_dashboard_df if not real_dashboard_df.empty else df.copy()
    data_mode = "실측·수집 데이터" if not real_dashboard_df.empty else "예시 데이터"
    page_header(
        "Insights",
        f"{data_mode}에서 다음 콘텐츠에 반복할 패턴과 중단할 패턴을 찾습니다.",
    )

    if real_dashboard_df.empty:
        st.info("아직 실제 수집 또는 Meta 동기화 데이터가 없어 예시 데이터를 표시합니다.")
    else:
        source_counts = dashboard_df["출처"].value_counts().to_dict()
        st.caption("데이터 출처: " + " · ".join(f"{name} {count}개" for name, count in source_counts.items()))

    filter_cols = st.columns([1.4, 1, 1])
    available_sources = sorted(str(value) for value in dashboard_df["출처"].dropna().unique())
    selected_sources = filter_cols[0].multiselect(
        "데이터 출처",
        available_sources,
        default=available_sources,
    )
    available_accounts = sorted(
        str(value) for value in dashboard_df.get("사용자", pd.Series(dtype=str)).dropna().unique() if str(value).strip()
    )
    selected_account = filter_cols[1].selectbox("Instagram 계정", ["전체"] + available_accounts)
    selected_period = filter_cols[2].selectbox("기간", ["전체", "최근 7일", "최근 30일", "최근 90일"])

    if selected_sources:
        dashboard_df = dashboard_df[dashboard_df["출처"].isin(selected_sources)].copy()
    else:
        dashboard_df = dashboard_df.iloc[0:0].copy()
    if selected_account != "전체":
        dashboard_df = dashboard_df[dashboard_df["사용자"].astype(str) == selected_account].copy()
    uploaded_at = pd.to_datetime(dashboard_df["업로드"], errors="coerce")
    period_days = {"최근 7일": 7, "최근 30일": 30, "최근 90일": 90}.get(selected_period)
    if period_days:
        dashboard_df = dashboard_df[uploaded_at >= pd.Timestamp.now() - pd.Timedelta(days=period_days)].copy()
        uploaded_at = pd.to_datetime(dashboard_df["업로드"], errors="coerce")
    if dashboard_df.empty:
        st.info("선택한 필터에 해당하는 릴스가 없습니다.")
        st.stop()

    insight_frame = dashboard_df.copy()
    insight_frame["저장률"] = insight_frame["저장"] / insight_frame["조회수"].replace(0, pd.NA) * 100
    best_save = insight_frame.sort_values("저장률", ascending=False, na_position="last").iloc[0]
    best_views = insight_frame.sort_values("조회수", ascending=False).iloc[0]
    st.info(
        f"이번 선택에서 **{best_save['릴스명']}**의 저장률이 가장 높고, "
        f"**{best_views['릴스명']}**이 가장 많은 조회를 만들었습니다. "
        "둘의 훅과 촬영 구도를 다음 프로젝트에서 우선 비교하세요."
    )
    published_projects = [
        item for item in list_projects(CONTENT_PROJECTS_PATH)
        if item.get("stage") == "posted"
    ]
    if published_projects:
        linked_rows = []
        for project in published_projects:
            media_id = str(project.get("instagram_media_id") or "")
            matched = dashboard_df[
                dashboard_df["릴스"].astype(str) == media_id
            ] if media_id else dashboard_df.iloc[0:0]
            measured = matched.iloc[0] if not matched.empty else None
            linked_rows.append({
                "Project": project.get("title"),
                "Published": project.get("published_at") or "-",
                "Views": int(measured["조회수"]) if measured is not None else None,
                "Saves": int(measured["저장"]) if measured is not None else None,
                "Measurement": "Connected" if measured is not None else "Waiting for Meta sync",
            })
        st.dataframe(pd.DataFrame(linked_rows), use_container_width=True, hide_index=True)

    recent_count = int((uploaded_at >= pd.Timestamp.now() - pd.Timedelta(days=7)).sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("수집된 릴스", f"{len(dashboard_df)}개", f"+{recent_count} 최근 7일")
    c2.metric("평균 점수", f"{dashboard_df['총점'].mean():.1f}점")
    c3.metric("S등급 릴스", f"{len(dashboard_df[dashboard_df['등급']=='S'])}개",
              f"전체의 {len(dashboard_df[dashboard_df['등급']=='S'])/len(dashboard_df)*100:.0f}%")
    c4.metric("평균 조회수", f"{int(dashboard_df['조회수'].mean()):,}")

    st.divider()
    col1, col2 = st.columns([3, 2])

    with col1:
        st.subheader("점수 분포")
        st.caption(f"평균 점수는 {dashboard_df['총점'].mean():.1f}점이며, 최고 점수는 {dashboard_df['총점'].max():.1f}점입니다.")
        fig = px.histogram(dashboard_df, x="총점", nbins=10, color_discrete_sequence=["#09cbea"],
                           labels={"총점": "성과 점수", "count": "릴스 수"}, title="릴스 성과 점수 분포")
        fig.update_layout(margin=dict(l=0, r=0, t=40, b=0), height=280,
                          plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font=dict(size=14))
        st.plotly_chart(fig, use_container_width=True, config=PLOT_CONFIG)

    with col2:
        st.subheader("등급별 현황")
        tc = dashboard_df["등급"].value_counts().reindex(["S", "A", "B", "C"], fill_value=0)
        fig2 = px.pie(values=tc.values, names=tc.index, hole=0.5,
                      color=tc.index,
                      color_discrete_map=TIER_COLORS)
        fig2.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=250,
                           paper_bgcolor="rgba(0,0,0,0)")
        st.caption("등급별 개수: " + ", ".join([f"{grade} {count}개" for grade, count in tc.items()]))
        st.plotly_chart(fig2, use_container_width=True, config=PLOT_CONFIG)

    st.divider()
    st.subheader("🏆 상위 10개 릴스")
    st.caption("사장님이 바로 맥락을 잡을 수 있도록 릴스 종류, 내용 설명, 원본 링크를 함께 보여줍니다.")
    top = dashboard_df.head(10)[[
        "릴스명", "어떤 영상인지", "링크", "출처", "총점", "등급", "조회수", "저장", "공유", "촬영구도", "길이(초)"
    ]].copy()
    top["조회수"] = top["조회수"].apply(lambda x: f"{x:,}")
    st.dataframe(
        top,
        use_container_width=True,
        hide_index=True,
        column_config={
            "릴스명": st.column_config.TextColumn("릴스 종류", width="small"),
            "어떤 영상인지": st.column_config.TextColumn("맥락", width="large"),
            "링크": st.column_config.LinkColumn("보기", display_text="릴스 열기", width="small"),
            "출처": st.column_config.TextColumn("자료", width="small"),
            "총점": st.column_config.NumberColumn("총점", format="%.1f"),
        },
    )

    st.divider()
    st.subheader("📈 점수 vs 조회수")
    st.caption("상위 릴스 중 조회수는 높은데 점수가 낮은 영상, 점수는 높은데 아직 덜 퍼진 영상을 비교합니다.")
    fig3 = px.scatter(dashboard_df, x="총점", y="조회수", color="등급", size="저장",
                      color_discrete_map=TIER_COLORS,
                      hover_data=["릴스명", "촬영구도", "길이(초)", "출처"])
    fig3.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=300,
                       plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig3, use_container_width=True, config=PLOT_CONFIG)


# ══════════════════════════════════════
# 🔍 릴스 분석
# ══════════════════════════════════════
elif menu == "Studio":
    page_header(
        "Studio",
        "아이디어를 대본과 촬영 목록으로 만들고, 촬영본을 검토해 게시 가능한 상태까지 이어갑니다.",
    )

    studio_projects = list_projects(CONTENT_PROJECTS_PATH)
    if studio_projects:
        project_options = [item["id"] for item in studio_projects]
        current_project_id = st.session_state.get("active_project_id")
        if current_project_id not in project_options:
            current_project_id = project_options[0]
        selected_project_id = st.selectbox(
            "Active project",
            project_options,
            index=project_options.index(current_project_id),
            format_func=lambda value: next(
                f"{item['title']} · {STAGE_LABELS.get(item.get('stage'), 'Idea')}"
                for item in studio_projects if item["id"] == value
            ),
        )
        st.session_state["active_project_id"] = selected_project_id
        studio_project = next(item for item in studio_projects if item["id"] == selected_project_id)
    else:
        studio_project = None
        st.info("먼저 Home에서 새 프로젝트를 만들거나 Radar에서 소재를 프로젝트로 저장하세요.")

    has_gemini_key = has_env("GEMINI_API_KEY") or has_env("GOOGLE_API_KEY")
    if not has_gemini_key:
        st.warning("Gemini API 키가 없어 실제 분석을 실행할 수 없습니다.")

    project_tab, tab0, tab1, tab2, tab3 = st.tabs(["Project", "Analyze", "Upload", "Library", "Queue"])

    with project_tab:
        if studio_project:
            stage_index = PROJECT_STAGES.index(studio_project.get("stage", "idea"))
            stage_columns = st.columns(len(PROJECT_STAGES))
            for index, (column, stage) in enumerate(zip(stage_columns, PROJECT_STAGES)):
                column.metric(STAGE_LABELS[stage], "Current" if index == stage_index else ("Done" if index < stage_index else "Next"))

            project_source = studio_project.get("source") or {}
            if project_source:
                source_col, link_col = st.columns([3, 1])
                source_col.caption(
                    f"Source: {project_source.get('type', 'saved idea')}"
                    + (f" · @{project_source.get('username')}" if project_source.get("username") else "")
                    + (f" · query {project_source.get('query')}" if project_source.get("query") else "")
                )
                if project_source.get("url"):
                    link_col.link_button("Open source", project_source["url"], use_container_width=True)

            with st.form(f"project_editor_{studio_project['id']}"):
                project_title = st.text_input("Project title", value=studio_project.get("title", ""))
                project_concept = st.text_area("Concept", value=studio_project.get("concept", ""), height=90)
                project_hook = st.text_area("Opening hook", value=studio_project.get("hook", ""), height=80)
                project_script = st.text_area("Script", value=studio_project.get("script", ""), height=220)
                project_shots = st.text_area(
                    "Shot list",
                    value="\n".join(studio_project.get("shot_list") or []),
                    placeholder="한 줄에 한 컷씩 입력하세요.",
                    height=150,
                )
                next_stage = st.selectbox(
                    "Stage",
                    PROJECT_STAGES,
                    index=stage_index,
                    format_func=lambda value: STAGE_LABELS[value],
                )
                publish_cols = st.columns(2)
                instagram_media_id = publish_cols[0].text_input(
                    "Instagram media ID",
                    value=studio_project.get("instagram_media_id", ""),
                    help="게시 후 Meta 동기화 결과와 프로젝트를 연결할 때 사용합니다.",
                )
                published_at = publish_cols[1].text_input(
                    "Published at",
                    value=studio_project.get("published_at", ""),
                    placeholder="YYYY-MM-DD HH:MM",
                )
                save_project = st.form_submit_button("Save project", type="primary", use_container_width=True)
            if save_project:
                update_project(
                    studio_project["id"],
                    {
                        "title": project_title,
                        "concept": project_concept,
                        "hook": project_hook,
                        "script": project_script,
                        "shot_list": [line.strip() for line in project_shots.splitlines() if line.strip()],
                        "stage": next_stage,
                        "instagram_media_id": instagram_media_id.strip(),
                        "published_at": published_at.strip(),
                    },
                    CONTENT_PROJECTS_PATH,
                )
                st.success("프로젝트를 저장했습니다.")
                st.rerun()

            edit_notes = studio_project.get("edit_notes") or []
            if edit_notes:
                st.markdown("**Review checklist**")
                for note in edit_notes:
                    st.checkbox(str(note), key=f"review_{studio_project['id']}_{hashlib.md5(str(note).encode()).hexdigest()}")
        else:
            if st.button("Create a project on Home", use_container_width=True):
                go_to_menu("Home")

    with tab0:
        collected = df[
            (df["출처"].isin(["실제 수집", "직접 추가", "Meta 실측"]))
            & (
                df["로컬영상"].apply(lambda value: bool(value) and Path(str(value)).exists())
                | df.get("원격영상", pd.Series(index=df.index, dtype=str)).fillna("").astype(str).ne("")
            )
        ].copy()

        if collected.empty:
            st.info("아직 바로 분석할 수 있는 저장 영상이 없습니다. 수집된 릴스를 다운로드하거나 직접 릴스를 추가해주세요.")
        else:
            options = collected.index.tolist()

            def option_label(index: int) -> str:
                row = collected.loc[index]
                return f"{row['릴스명']} · 조회수 {int(row['조회수']):,} · {row['등급']}등급"

            selected_index = st.selectbox(
                "분석할 릴스",
                options,
                format_func=option_label,
                help="이미 다운로드된 상위 릴스를 선택하면 파일 업로드 없이 바로 분석할 수 있습니다.",
            )
            selected = collected.loc[selected_index]

            info1, info2, info3 = st.columns(3)
            info1.metric("총점", f"{float(selected['총점']):.1f}")
            info2.metric("조회수", f"{int(selected['조회수']):,}")
            info3.metric("공유", f"{int(selected['공유']):,}")

            st.markdown(f"**맥락**: {selected['어떤 영상인지']}")
            if str(selected.get("링크", "")).strip():
                st.link_button("원본 릴스 열기", selected["링크"], use_container_width=True)
            else:
                st.caption("원본 릴스 링크가 저장되어 있지 않습니다.")
            selected_local = str(selected.get("로컬영상", ""))
            selected_remote = str(selected.get("원격영상", ""))
            st.video(selected_local if selected_local and Path(selected_local).exists() else selected_remote)

            run_col, queue_col = st.columns(2)
            run_selected_now = run_col.button(
                "지금 분석",
                type="primary",
                use_container_width=True,
                disabled=not has_gemini_key,
            )
            queue_selected = queue_col.button(
                "백그라운드 예약",
                use_container_width=True,
                disabled=not has_gemini_key,
            )
            if queue_selected:
                payload = {
                    "caption": str(selected.get("캡션", "")),
                    "title": f"{selected['릴스']}_{selected['릴스명']}",
                    "source_id": str(selected.get("릴스", "")),
                }
                if selected_local and Path(selected_local).exists():
                    payload["video_path"] = str(Path(selected_local).resolve())
                    kind = "video_analysis_file"
                    source_key = payload["video_path"]
                else:
                    payload["video_url"] = selected_remote
                    kind = "video_analysis_url"
                    source_key = selected_remote
                dedupe = hashlib.sha256(f"{kind}:{source_key}:{payload['caption']}".encode("utf-8")).hexdigest()
                job = enqueue_job(kind, payload, dedupe_key=dedupe, owner_id=JOB_OWNER_ID, path=JOB_DB_PATH)
                st.success(f"분석 작업을 예약했습니다. 작업 ID: {job['id'][:8]}")

            if run_selected_now:
                try:
                    with st.spinner("Gemini가 선택한 릴스 프레임을 분석 중입니다..."):
                        if selected_local and Path(selected_local).exists():
                            analysis = analyze_reel_from_file(selected_local, caption=str(selected.get("캡션", "")))
                        else:
                            analysis = analyze_reel_from_url(selected_remote, caption=str(selected.get("캡션", "")))
                    report_text, report_path = write_analysis_report(
                        analysis,
                        f"{selected['릴스']}_{selected['릴스명']}",
                    )
                    if selected.get("출처") in {"직접 추가", "Meta 실측"}:
                        upsert_user_reel({
                            "릴스": selected["릴스"],
                            "릴스명": selected["릴스명"],
                            "링크": selected.get("링크", ""),
                            "업종": btype,
                            "analysis": analysis,
                            "촬영구도": ", ".join(analysis.get("camera_angles", [])) or selected.get("촬영구도", "-"),
                            "BGM": analysis.get("bgm_mood", selected.get("BGM", "-")),
                        })
                        st.cache_data.clear()
                        if selected.get("instagram_media_id") and has_env("SUPABASE_URL") and has_env("SUPABASE_ANON_KEY"):
                            try:
                                save_analysis_for_instagram_media(selected["instagram_media_id"], analysis)
                            except Exception as cloud_exc:
                                st.warning(f"분석은 로컬에 저장됐지만 Supabase 저장은 실패했습니다: {cloud_exc}")
                    st.session_state["latest_analysis"] = analysis
                    attach_analysis_to_active_project(analysis)
                    show_analysis_result(analysis, report_text, report_path)
                except Exception as exc:
                    st.error(f"분석 실패: {exc}")

    with tab1:
        with st.form("reel_analysis_form", clear_on_submit=False):
            reel_type_input = st.text_input(
                "릴스 종류",
                placeholder="예: 소금빵 컷팅, 신상 카페 투어, 네일 전후 비교",
                help="내 릴스 목록에서 짧게 알아볼 이름입니다.",
            )
            source_url_input = st.text_input(
                "원본 릴스 링크",
                placeholder="https://www.instagram.com/reel/...",
                help="선택 사항입니다. 나중에 원본 릴스로 바로 이동할 때 사용합니다.",
            )
            uploaded = st.file_uploader(
                "릴스 영상 파일",
                type=["mp4", "mov"],
                help="MP4 또는 MOV 형식의 릴스 영상을 업로드하세요.",
            )
            caption_input = st.text_area(
                "본문 캡션",
                height=120,
                placeholder="예: 성수동 신상 베이커리 카페, 갓 구운 소금빵이 나오는 장면...",
                help="캡션을 입력하면 후킹 문구와 저장 유도 패턴까지 함께 분석합니다.",
            )
            caption_len = len(caption_input.strip())
            uploaded_too_large = bool(uploaded and uploaded.size > MAX_UPLOAD_MB * 1024 * 1024)
            if uploaded:
                file_size_mb = uploaded.size / 1024 / 1024
                st.caption(f"업로드 파일: {uploaded.name} · {file_size_mb:.1f}MB")
                if uploaded_too_large:
                    st.error(f"파일이 너무 큽니다. {MAX_UPLOAD_MB}MB 이하 영상만 분석할 수 있습니다.")

            if caption_input and caption_len < 10:
                st.error("캡션이 너무 짧습니다. 최소 10자 이상 입력하면 분석 품질이 좋아집니다.")
            elif caption_input:
                st.caption(f"캡션 {caption_len}자 입력됨")

            save_to_library = st.checkbox("분석 후 내 릴스 목록에 저장", value=True)
            run_in_background = st.checkbox(
                "백그라운드에서 분석",
                value=False,
                help="화면을 닫아도 별도 워커가 분석을 이어갑니다.",
            )

            submitted = st.form_submit_button(
                "AI 분석 시작",
                type="primary",
                use_container_width=True,
                disabled=not has_gemini_key or uploaded_too_large,
            )

        if uploaded:
            st.video(uploaded)

        if submitted:
            if not uploaded:
                st.error("영상을 먼저 업로드해주세요.")
            elif uploaded_too_large:
                st.error(f"파일이 너무 큽니다. {MAX_UPLOAD_MB}MB 이하 영상만 분석할 수 있습니다.")
            elif Path(uploaded.name).suffix.lower() not in [".mp4", ".mov"]:
                st.error("지원하지 않는 파일 형식입니다. MP4 또는 MOV 파일을 업로드해주세요.")
            elif caption_input and caption_len < 10:
                st.error("캡션을 입력하려면 최소 10자 이상 작성해주세요.")
            else:
                suffix = Path(uploaded.name).suffix or ".mp4"
                report_path = None
                tmp_path = None
                saved_video_path = None

                try:
                    title = reel_type_input.strip() or make_reel_title({"caption": caption_input}, btype)
                    if run_in_background:
                        queued_path = save_uploaded_reel(uploaded, suffix)
                        dedupe = hashlib.sha256(
                            f"video_analysis_file:{queued_path.resolve()}:{caption_input}".encode("utf-8")
                        ).hexdigest()
                        job = enqueue_job(
                            "video_analysis_file",
                            {
                                "video_path": str(queued_path.resolve()),
                                "caption": caption_input,
                                "title": title,
                                "source_url": source_url_input.strip(),
                                "business_type": btype,
                                "save_to_library": save_to_library,
                            },
                            dedupe_key=dedupe,
                            owner_id=JOB_OWNER_ID,
                            path=JOB_DB_PATH,
                        )
                        st.success(f"백그라운드 작업을 예약했습니다. 작업 ID: {job['id'][:8]}")
                        st.info("작업 대기열 탭에서 진행률과 결과를 확인할 수 있습니다.")
                        st.stop()

                    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                        tmp.write(uploaded.getbuffer())
                        tmp_path = tmp.name

                    with st.spinner("Gemini가 영상 프레임을 분석 중입니다..."):
                        analysis = analyze_reel_from_file(tmp_path, caption=caption_input)
                    st.session_state["latest_analysis"] = analysis
                    attach_analysis_to_active_project(analysis)

                    report_text, report_path = write_analysis_report(
                        analysis,
                        f"{title}_{Path(uploaded.name).stem}",
                    )

                    if save_to_library:
                        saved_video_path = save_uploaded_reel(uploaded, suffix)
                        upsert_user_reel({
                            "릴스": saved_video_path.stem,
                            "릴스명": title,
                            "어떤 영상인지": shorten_text(
                                analysis.get("analysis_summary") or caption_input or f"{btype} 업종 직접 추가 릴스",
                                72,
                            ),
                            "원문": first_caption_line(caption_input) if caption_input else title,
                            "캡션": caption_input,
                            "링크": source_url_input.strip(),
                            "로컬영상": str(saved_video_path),
                            "업종": btype,
                            "store_id": (st.session_state.get("store_profile") or {}).get("store_id", ""),
                            "조회수": 0,
                            "좋아요": 0,
                            "저장": 0,
                            "공유": 0,
                            "총점": 72,
                            "등급": "B",
                            "길이(초)": 0,
                            "촬영구도": ", ".join(analysis.get("camera_angles", [])) or "-",
                            "BGM": analysis.get("bgm_mood", "-"),
                            "BGM곡": "",
                            "analysis": analysis,
                            "insights": {},
                            "업로드": datetime.now().isoformat(timespec="seconds"),
                        })
                        st.cache_data.clear()
                        st.success("내 릴스 목록에 저장했습니다. 새로고침하면 목록에 반영됩니다.")

                    show_analysis_result(analysis, report_text, report_path)
                except Exception as exc:
                    st.error(f"분석 실패: {exc}")
                finally:
                    if tmp_path:
                        Path(tmp_path).unlink(missing_ok=True)

    with tab2:
        st.subheader(f"내 {btype} 릴스 목록")
        tier_filter = st.multiselect("등급 필터", ["S", "A", "B", "C"], default=["S", "A", "B", "C"])
        filtered = df[df["등급"].isin(tier_filter)]
        for _, row in filtered.head(8).iterrows():
            title = row.get("릴스명") or row.get("릴스")
            source = row.get("출처", "예시")
            views = int(row.get("조회수", 0))
            with st.expander(f"[{row['등급']}] {title} · {source} · {row['총점']}점 | 조회수 {views:,}"):
                cc1, cc2, cc3, cc4 = st.columns(4)
                cc1.metric("좋아요", f"{int(row['좋아요']):,}")
                cc2.metric("저장", f"{int(row['저장']):,}")
                cc3.metric("공유", f"{int(row['공유']):,}")
                cc4.metric("길이", f"{row['길이(초)']}초")
                st.markdown(f"**맥락**: {row.get('어떤 영상인지', '-')}")
                st.markdown(f"촬영 구도: `{row['촬영구도']}` | BGM: `{row['BGM']}`")
                link = str(row.get("링크", "")).strip()
                local_video = str(row.get("로컬영상", "")).strip()
                action_cols = st.columns([1, 1])
                if link:
                    action_cols[0].link_button("원본 릴스 열기", link, use_container_width=True)
                if local_video and Path(local_video).exists():
                    action_cols[1].caption("저장된 영상 있음")
                    st.video(local_video)

    with tab3:
        st.subheader("백그라운드 분석 작업")
        st.caption("워커 실행: `scripts\\run_job_worker.ps1` · 한 건만 실행: `scripts\\run_job_worker.ps1 --once`")
        jobs = list_jobs(limit=25, owner_id=JOB_OWNER_ID, path=JOB_DB_PATH)
        if not jobs:
            st.info("예약된 분석 작업이 없습니다.")
        status_labels = {
            "pending": "대기",
            "running": "분석 중",
            "completed": "완료",
            "failed": "실패",
            "cancelled": "취소",
        }
        for job in jobs:
            label = status_labels.get(job["status"], job["status"])
            with st.expander(f"{label} · {job['kind']} · {job['id'][:8]}"):
                st.progress(int(job.get("progress") or 0))
                st.caption(f"시도 {job.get('attempts', 0)}/{job.get('max_attempts', 0)} · 생성 {job.get('created_at', '-')}")
                if job.get("error"):
                    st.error(job["error"])
                if job["status"] in {"pending", "running"} and st.button(
                    "작업 취소" if job["status"] == "pending" else "분석 중단 요청",
                    key=f"cancel_{job['id']}",
                ):
                    cancel_job(job["id"], owner_id=JOB_OWNER_ID, path=JOB_DB_PATH)
                    st.rerun()
                result = job.get("result") or {}
                if job["status"] == "completed" and result.get("analysis"):
                    if st.button("분석 결과 열기", key=f"open_job_{job['id']}"):
                        analysis = result["analysis"]
                        st.session_state["latest_analysis"] = analysis
                        attach_analysis_to_active_project(analysis)
                        payload = job.get("payload") or {}
                        if payload.get("save_to_library") and payload.get("video_path"):
                            video_path = Path(payload["video_path"])
                            upsert_user_reel({
                                "릴스": video_path.stem,
                                "릴스명": payload.get("title") or video_path.stem,
                                "어떤 영상인지": shorten_text(analysis.get("analysis_summary") or payload.get("caption") or "직접 추가 릴스", 72),
                                "원문": first_caption_line(payload.get("caption", "")),
                                "캡션": payload.get("caption", ""),
                                "링크": payload.get("source_url", ""),
                                "로컬영상": str(video_path),
                                "업종": payload.get("business_type") or btype,
                                "store_id": (st.session_state.get("store_profile") or {}).get("store_id", ""),
                                "조회수": 0,
                                "좋아요": 0,
                                "저장": 0,
                                "공유": 0,
                                "총점": float(analysis.get("overall_score") or 72),
                                "등급": "B",
                                "길이(초)": int(analysis.get("duration_seconds") or 0),
                                "촬영구도": ", ".join(analysis.get("camera_angles", [])) or "-",
                                "BGM": analysis.get("bgm_mood", "-"),
                                "BGM곡": "",
                                "analysis": analysis,
                                "insights": {},
                                "업로드": datetime.now().isoformat(timespec="seconds"),
                            })
                            st.cache_data.clear()
                        st.success("분석 결과를 프로젝트 Review 단계와 Playbook에 연결했습니다.")
                    st.caption(f"보고서: {result.get('report_path', '-')}")


# ══════════════════════════════════════
# 📋 AI 릴스 가이드
# ══════════════════════════════════════
elif menu == "Playbook":
    page_header(
        "Playbook",
        "내 게시 결과에서 반복해서 통했던 패턴을 확인하고 다음 프로젝트에 적용합니다.",
    )

    top_df = df.head(10).copy()
    source_reels = get_guide_source_reels(top_df, 3)
    camera_guides = top_camera_guides(top_df)
    audio_use = st.selectbox(
        "BGM 사용 목적",
        ["organic_business", "branded_content", "paid_campaign"],
        format_func=lambda value: {
            "organic_business": "비즈니스 계정 일반 게시",
            "branded_content": "협찬·브랜디드 콘텐츠",
            "paid_campaign": "유료 광고",
        }[value],
        help="같은 음원도 게시 목적에 따라 허용 범위가 달라질 수 있습니다.",
    )
    track_rows = annotate_tracks(
        trend_tracks_for(btype, top_df),
        intended_use=audio_use,
        registry_path=AUDIO_RIGHTS_REGISTRY,
    )
    hashtags = TREND_HASHTAGS.get(btype, TREND_HASHTAGS["카페"])
    hashtag_text = " ".join(hashtags)
    average_top_score = top_df["총점"].mean() if not top_df.empty else 0
    recommended_length = "30~45초"
    primary_camera = camera_guides[0][0] if camera_guides else "클로즈업"
    current_store_profile = st.session_state.get("store_profile") or {}
    creator_memory = learn_creator_patterns(
        load_user_reels(btype),
        store_id=current_store_profile.get("store_id"),
    )

    f1, f2, f3 = st.columns(3)
    f1.metric("추천 영상 길이", f"{creator_memory['recommended_length']}초 안팎" if creator_memory.get("recommended_length") else recommended_length)
    f2.metric("먼저 찍을 구도", primary_camera)
    f3.metric("상위 릴스 평균 점수", f"{average_top_score:.1f}점")

    st.markdown("**Evidence-backed patterns**")
    st.caption(creator_memory["message"])
    if creator_memory.get("top_cameras"):
        st.markdown(
            f"잘된 구도: `{', '.join(creator_memory['top_cameras'])}`"
            + (f" · 권장 길이: `{creator_memory['recommended_length']}초 안팎`" if creator_memory.get("recommended_length") else "")
        )
    if creator_memory.get("patterns"):
        pattern_df = pd.DataFrame(creator_memory["patterns"])
        st.dataframe(
            pattern_df[["feature", "value", "count", "lift_percent", "confidence"]],
            use_container_width=True,
            hide_index=True,
            column_config={"lift_percent": st.column_config.NumberColumn("내 기준 상승률", format="%+.1f%%")},
        )
    excluded = creator_memory.get("excluded") or {}
    if sum(excluded.values()):
        st.caption(
            f"학습 제외: 실측 없음 {excluded.get('no_measured_result', 0)}개 · "
            f"영상 분석 없음 {excluded.get('no_analysis', 0)}개 · 다른 매장 {excluded.get('other_store', 0)}개"
        )

    st.divider()
    st.subheader("This week's direction")
    trend_summary = (
        f"이번 주 {btype} 릴스는 **{primary_camera}** 구도로 첫 장면을 빠르게 보여주고, "
        f"**{track_rows[0]['곡명']}** 같은 익숙한 음원에 맞춰 메뉴/공간/손동작 컷을 짧게 붙이는 흐름이 좋습니다. "
        "아래에서 내 가게 설명을 넣으면 이 흐름을 내 메뉴와 매장 상황에 맞춰 바꿔줍니다."
    )
    st.markdown(trend_summary)

    st.markdown("**가이드 생성 근거 릴스**")
    if source_reels.empty:
        st.info("아직 분석된 릴스가 없습니다. 릴스를 수집하거나 직접 추가하면 이 가이드의 근거가 더 분명하게 표시됩니다.")
    else:
        evidence_cols = st.columns(len(source_reels))
        for col, (_, row) in zip(evidence_cols, source_reels.iterrows()):
            with col:
                st.metric("총점", f"{float(row['총점']):.1f}점")
                st.markdown(f"**{row['릴스명']}**")
                st.caption(row.get("어떤 영상인지", ""))
                st.caption(f"구도: {row.get('촬영구도', '-')} · 출처: {row.get('출처', '-')}")
                if str(row.get("링크", "")).strip():
                    st.link_button("릴스 보기", row["링크"], use_container_width=True)

    st.divider()
    st.subheader("Build from Playbook")
    st.caption("긴 문장으로 적지 않아도 됩니다. 아래 칸만 채우면 각 트렌드 섹션에서 내 가게용 추천을 붙여줍니다.")
    with st.form("store_guide_form"):
        saved_store = st.session_state.get("store_profile", {})
        col_a, col_b = st.columns(2)
        with col_a:
            store_name = st.text_input(
                "가게 이름",
                placeholder="예: 부자카페 성수점",
                value=saved_store.get("name", ""),
            )
            store_place = st.text_input(
                "지역/상권",
                placeholder="예: 성수동, 홍대입구역, 강남역",
                value=saved_store.get("place", ""),
            )
            store_menu = st.text_input(
                "대표 메뉴/상품",
                placeholder="예: 소금빵, 말차라떼, 네일 전후, 하체 PT",
                value=saved_store.get("menu", ""),
            )
            store_strength = st.text_input(
                "가게 강점",
                placeholder="예: 조용한 분위기, 수제 디저트, 전후 차이, 가성비",
                value=saved_store.get("strength", ""),
            )
        with col_b:
            store_audience = st.text_input(
                "주요 손님층",
                placeholder="예: 혼자 오는 손님, 데이트 손님, 직장인 점심",
                value=saved_store.get("audience", ""),
            )
            store_goal = st.selectbox(
                "릴스에서 유도할 행동",
                ["저장", "방문", "예약", "DM 문의", "팔로우"],
                index=["저장", "방문", "예약", "DM 문의", "팔로우"].index(saved_store.get("goal", "저장"))
                if saved_store.get("goal", "저장") in ["저장", "방문", "예약", "DM 문의", "팔로우"] else 0,
            )
            store_note = st.text_input(
                "이번 주에 특히 밀고 싶은 것",
                placeholder="예: 신메뉴, 주말 한정, 웨이팅 없는 시간대",
                value=saved_store.get("note", ""),
            )
        st.caption(
            "예시: 지역/상권=성수동, 대표 메뉴=소금빵, 강점=조용한 분위기, "
            "주요 손님층=혼자 오는 손님, 유도 행동=저장"
        )
        guide_submitted = st.form_submit_button("아래 가이드에 내 가게 반영하기", type="primary", use_container_width=True)

    required_store_fields = [store_name, store_place, store_menu, store_strength]
    if guide_submitted and not all(value.strip() for value in required_store_fields):
        st.error("가게 이름, 지역/상권, 대표 메뉴/상품, 가게 강점은 꼭 입력해주세요.")
    elif guide_submitted:
        store_profile = {
            "name": store_name.strip(),
            "place": store_place.strip(),
            "menu": store_menu.strip(),
            "strength": store_strength.strip(),
            "audience": store_audience.strip(),
            "goal": store_goal,
            "note": store_note.strip(),
        }
        store_profile = save_store_profile(store_profile)
        st.session_state["store_profile"] = store_profile
        creator_memory = learn_creator_patterns(
            load_user_reels(btype),
            store_id=store_profile.get("store_id"),
        )
        st.session_state["personalized_guide"] = personalize_with_memory(
            build_personalized_guide(
                store_profile,
                btype,
                primary_camera,
                track_rows,
                hashtags,
            ),
            creator_memory,
        )
        st.success("내 가게 정보를 아래 트렌드 가이드에 반영했습니다.")

    personalized = st.session_state.get("personalized_guide")
    if personalized:
        keywords = personalized["keywords"]
        st.caption(f"현재 반영 중: {keywords['place']} / {keywords['menu']} / {keywords['strength']}")
        angle_names = ["Sales", "Story", "Curiosity"]
        selected_angle = st.radio("Content angle", angle_names, horizontal=True)
        angle_index = angle_names.index(selected_angle)
        selected_hook = personalized["hooks"][min(angle_index, len(personalized["hooks"]) - 1)]
        st.markdown(f"**Selected hook**: {selected_hook}")
        active_projects = list_projects(CONTENT_PROJECTS_PATH)
        if active_projects:
            target_project_id = st.selectbox(
                "Apply to project",
                [item["id"] for item in active_projects],
                index=next(
                    (index for index, item in enumerate(active_projects) if item["id"] == st.session_state.get("active_project_id")),
                    0,
                ),
                format_func=lambda value: next(item["title"] for item in active_projects if item["id"] == value),
            )
            if st.button("Apply Playbook to Studio", type="primary", use_container_width=True):
                updated = update_project(
                    target_project_id,
                    {
                        "hook": selected_hook,
                        "script": "\n\n".join(personalized["captions"]),
                        "shot_list": personalized["scenes"],
                        "stage": "script",
                    },
                    CONTENT_PROJECTS_PATH,
                )
                if updated:
                    st.session_state["active_project_id"] = target_project_id
                    st.success("선택한 각도를 Studio 프로젝트에 적용했습니다.")
    else:
        st.info("가게 정보를 입력하면 BGM, 촬영 구도, 해시태그, 후킹·편집 스토리보드가 아래에 생성됩니다.")
        st.stop()

    latest_analysis = st.session_state.get("latest_analysis") or {}
    st.markdown("**최근 분석에서 개선 대본 만들기**")
    if latest_analysis:
        st.caption("최근 영상의 실제 정체 구간과 우선 수정 항목을 다음 대본과 촬영 목록에 직접 반영합니다.")
        if st.button("분석 반영 AI 대본·촬영 목록 생성", type="primary", use_container_width=True):
            try:
                with st.spinner("이전 영상의 문제를 고치는 촬영 대본을 만드는 중입니다..."):
                    st.session_state["production_plan"] = generate_revised_production_plan(
                        latest_analysis,
                        st.session_state.get("store_profile") or {},
                    )
                    plan = st.session_state["production_plan"]
                    project_id = st.session_state.get("active_project_id")
                    if project_id:
                        update_project(
                            project_id,
                            {
                                "title": plan.get("title") or "개선 릴스",
                                "hook": plan.get("hook") or "",
                                "script": plan.get("caption_first_line") or "",
                                "shot_list": [
                                    f"{shot.get('start_seconds', 0)}~{shot.get('end_seconds', 0)}초 · "
                                    f"{shot.get('shot', shot.get('on_screen_text', '촬영 컷'))}"
                                    for shot in plan.get("shots", [])
                                ],
                                "stage": "script",
                            },
                            CONTENT_PROJECTS_PATH,
                        )
                st.success("개선 대본과 촬영 목록을 생성했습니다.")
            except Exception as exc:
                st.error(f"개선 대본 생성 실패: {exc}")
    else:
        st.info("릴스 분석 메뉴에서 영상을 먼저 분석하면 그 결과를 다음 촬영안에 반영할 수 있습니다.")

    st.divider()
    st.subheader("🎵 인기 BGM 추천과 편집 방식")
    st.caption("상위 릴스의 편집 리듬을 기준으로 추천합니다. 실제 수집 릴스에 곡명이 들어오면 그 곡을 우선 보여줍니다.")
    if personalized:
        st.markdown("**내 가게 추천 BGM**")
        st.markdown(
            f"`{personalized['track']['곡명']}` 추천: {personalized['track_reason']} "
            f"{personalized['track']['편집법']}"
        )
        selected_rights = personalized["track"].get("rights") or {}
        if selected_rights.get("level") != "safe":
            st.warning(
                "이 곡은 트렌드·편집 참고용이며 현재 상태로는 상업 사용을 권장하지 않습니다. "
                + selected_rights.get("safe_alternative", "권리 증빙이 가능한 음원으로 교체하세요.")
            )
            st.link_button("Meta Sound Collection 열기", "https://www.facebook.com/sound/collection/", use_container_width=True)
        st.caption(storyboard_evidence_text(source_reels))
    for track in track_rows:
        with st.expander(f"{track['곡명']} · {track['아티스트']}"):
            st.markdown(f"**편집 포인트**: {track['편집법']}")
            rights = track.get("rights") or {}
            st.warning(f"음원 권리: {rights.get('status', '사용 전 확인 필요')} · {rights.get('detail', '')}")
            if rights.get("safe_alternative"):
                st.caption("안전한 대안: " + rights["safe_alternative"])
            st.markdown(
                "- 첫 1초에는 가장 맛있거나 예쁜 장면을 먼저 둡니다.\n"
                "- 박자가 바뀌는 순간마다 메뉴, 공간, 사람 손동작 컷을 바꿉니다.\n"
                "- 노래 제목은 Instagram 또는 CapCut 음원 검색창에 그대로 입력해 확인합니다."
            )
            if personalized and track["곡명"] == personalized["track"]["곡명"]:
                st.markdown("**내 가게 적용**")
                st.markdown(f"- 이 음원에는 `{personalized['keywords']['menu']}`가 등장하는 첫 장면을 후렴 시작점에 맞추는 방식이 좋습니다.")
                st.markdown(f"- 편집 포인트: {personalized['track']['편집법']}")

    with st.expander("음원 사용 권리 확인 기록"):
        with st.form("audio_rights_form"):
            verified_track = st.selectbox("확인한 음원", [track["곡명"] for track in track_rows])
            verified_source = st.selectbox(
                "확인한 출처",
                ["meta_sound_collection", "owned", "commissioned", "licensed_by_business", "instagram_licensed_music"],
                format_func=lambda value: {
                    "meta_sound_collection": "Meta Sound Collection",
                    "owned": "직접 제작·권리 보유",
                    "commissioned": "외주 제작 후 상업권 확보",
                    "licensed_by_business": "별도 상업 라이선스 구매",
                    "instagram_licensed_music": "Instagram 라이선스 음악 라이브러리",
                }[value],
            )
            verified_license = st.text_input("라이선스 또는 확인 내용", placeholder="예: Sound Collection에서 비즈니스 사용 확인")
            verified_evidence = st.text_input("증빙 링크 또는 문서 위치", placeholder="https://... 또는 계약서 파일명")
            verified_file = st.file_uploader("증빙 파일", type=["pdf", "png", "jpg", "jpeg"], key="audio_evidence_file")
            verified_expiry = st.text_input("만료일", placeholder="YYYY-MM-DD · 영구 권한이면 비워두세요")
            verified_notes = st.text_input("메모", placeholder="사용 지역, 기간, 광고 허용 여부")
            save_audio_rights = st.form_submit_button("권리 확인 기록 저장", use_container_width=True)
        if save_audio_rights:
            if not verified_license.strip():
                st.error("확인 내용을 입력해주세요.")
            else:
                expiry_valid = True
                if verified_expiry.strip():
                    try:
                        datetime.strptime(verified_expiry.strip(), "%Y-%m-%d")
                    except ValueError:
                        expiry_valid = False
                        st.error("만료일은 YYYY-MM-DD 형식으로 입력해주세요.")
                evidence_path = ""
                if expiry_valid and verified_file:
                    evidence_dir = USER_REELS_DIR / "audio_evidence"
                    evidence_dir.mkdir(parents=True, exist_ok=True)
                    safe_evidence_name = re.sub(r'[^0-9A-Za-z가-힣._-]+', "_", verified_file.name)
                    file_digest = hashlib.sha256(verified_file.getbuffer()).hexdigest()[:12]
                    evidence_target = evidence_dir / f"{file_digest}_{safe_evidence_name}"
                    evidence_target.write_bytes(verified_file.getbuffer())
                    evidence_path = str(evidence_target)
                if not expiry_valid:
                    st.stop()
                save_rights_verification(
                    verified_track,
                    verified_source,
                    verified_license.strip(),
                    verified_evidence.strip(),
                    verified_notes.strip(),
                    evidence_path=evidence_path,
                    expires_at=verified_expiry.strip(),
                    path=AUDIO_RIGHTS_REGISTRY,
                )
                st.success("음원 권리 확인 기록을 저장했습니다. 다음 새로고침부터 추천에 반영됩니다.")

    st.divider()
    st.subheader("📷 인기 촬영 구도와 휴대폰 위치")
    if personalized and personalized["camera"] not in [name for name, _, _ in camera_guides]:
        guide = CAMERA_GUIDES.get(personalized["camera"])
        if guide:
            camera_guides.append((personalized["camera"], 0, guide))
    ac = top_df["촬영구도"].value_counts()
    fig = px.bar(x=ac.index, y=ac.values, color_discrete_sequence=["#09cbea"],
                 labels={"x": "구도", "y": "상위 10개 중 등장 횟수"})
    fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=220,
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, use_container_width=True, config=PLOT_CONFIG)
    if personalized:
        st.markdown("**내 가게 추천 구도**")
        st.markdown(
            f"`{personalized['camera']}` 추천: {personalized['camera_reason']}"
        )

    for camera_name, count, guide in camera_guides:
        with st.expander(f"{camera_name} · 상위 릴스 {count}개에서 사용"):
            visual_col, text_col = st.columns([1, 2])
            with visual_col:
                st.markdown(render_shot_diagram(guide.get("그림", "front")), unsafe_allow_html=True)
            with text_col:
                st.markdown(f"**무슨 구도인지**: {guide['한줄']}")
                st.markdown(f"**휴대폰 위치**: {guide['찍는법']}")
                st.markdown(f"**피사체 위치**: {guide['위치']}")
            st.info("촬영 전 화면에 3x3 격자를 켜고, 메뉴나 사람이 가운데 칸 또는 가운데 아래 칸에 걸치게 맞추면 실패가 줄어듭니다.")
            st.caption(camera_evidence_text(top_df, camera_name))
            if personalized:
                st.markdown("**내 가게 적용**")
                if camera_name == personalized["camera"]:
                    st.markdown("\n".join([f"- {scene}" for scene in personalized["scenes"][:3]]))
                else:
                    st.markdown(
                        f"- `{personalized['keywords']['menu']}`를 이 구도로 보조 컷으로 찍어두면 메인 컷 사이 전환 장면으로 쓰기 좋습니다."
                    )

    st.divider()
    st.subheader("📱 휴대폰 구도 코치")
    st.caption("QR을 휴대폰으로 찍으면 카메라 화면 위에 구도 가이드가 뜨고, 음성으로 촬영 위치를 안내하는 별도 웹앱이 열립니다.")
    production_plan = st.session_state.get("production_plan") or {}
    storyboard_steps = (
        production_plan_to_storyboard(production_plan)
        if production_plan.get("shots")
        else build_storyboard_steps(btype, primary_camera, personalized, latest_analysis)
    )
    compact_shots = [
        {"title": step["title"], "guide": step["shoot"], "text": step["subtitle"]}
        for step in storyboard_steps
    ]
    shots_token = base64.urlsafe_b64encode(
        json.dumps(compact_shots, ensure_ascii=False).encode("utf-8")
    ).decode("ascii").rstrip("=")
    coach_params = {
        "mode": {"탑뷰": "topview", "클로즈업": "closeup", "정면샷": "front", "팔로잉샷": "following"}.get(
            personalized.get("camera", primary_camera), "topview"
        ),
        "menu": personalized["keywords"]["menu"],
        "hook": personalized["hooks"][0],
        "shots": shots_token,
        "return": get_app_return_url(),
    }
    coach_url = f"{get_mobile_coach_url()}?{urlencode(coach_params)}"
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=220x220&data={quote(coach_url, safe='')}"
    qr_col, link_col = st.columns([1, 2])
    with qr_col:
        st.image(qr_url, caption="휴대폰으로 스캔")
    with link_col:
        st.markdown("**사용 흐름**")
        st.markdown(
            "\n".join([
                "1. 휴대폰이 이 PC와 같은 와이파이에 연결되어 있는지 확인합니다.",
                "2. QR을 스캔해 모바일 구도 코치 웹앱을 엽니다.",
                "3. 원하는 구도를 고르면 화면 위에 음식/컵/손 위치 가이드가 뜹니다.",
                "4. 음성 안내를 켜면 촬영 중 어디로 움직일지 계속 알려줍니다.",
            ])
        )
        st.link_button("모바일 구도 코치 열기", coach_url, use_container_width=True)
        st.code(coach_url, language=None)
    st.info("현재 버전은 카메라 오버레이와 음성 안내로 촬영자가 따라 찍게 만드는 앱형 MVP입니다. 휴대폰 브라우저에서 카메라가 막히면 HTTPS 배포 주소가 필요합니다.")

    st.divider()
    st.subheader("🔖 인기 해시태그")
    st.caption("아래 묶음을 복사해서 캡션 마지막 줄에 붙여넣으면 됩니다. 너무 많아 보이면 앞의 6~8개만 사용하세요.")
    st.markdown(" ".join([f'<span class="hook-tag">{tag}</span>' for tag in hashtags]), unsafe_allow_html=True)
    st.code(hashtag_text, language=None)
    if personalized:
        st.markdown("**내 가게 적용**")
        st.code(" ".join(personalized["hashtags"]), language=None)

    st.divider()
    st.subheader(f"✂️ 이번 주 {btype} 릴스 후킹·편집 스토리보드")
    st.caption("후킹 패턴과 편집 순서를 합친 촬영 보드입니다. 각 그림은 휴대폰 화면 안에서 피사체와 문구를 어디에 둘지 보여줍니다.")
    st.info(storyboard_evidence_text(source_reels))
    if production_plan.get("shots"):
        p1, p2 = st.columns(2)
        p1.metric("개선 대본 목표 길이", f"{float(production_plan.get('target_duration_seconds', 0)):.0f}초")
        p2.metric("촬영 컷", f"{len(production_plan['shots'])}개")
        st.markdown(f"**대본 제목**: {production_plan.get('title', '-')}")
        st.markdown(f"**첫 문장**: {production_plan.get('hook', '-')}")
    st.markdown(render_motion_storyboard(storyboard_steps), unsafe_allow_html=True)
    st.markdown("**컷별 상세 보드**")
    for step in storyboard_steps:
        st.markdown(render_storyboard_card(step), unsafe_allow_html=True)

    export_lines = [f"# {btype} 릴스 촬영·편집 보드", ""]
    for step in storyboard_steps:
        export_lines.extend([
            f"## {step['title']}",
            f"- 화면 문구: {step['subtitle']}",
            f"- 촬영: {step['shoot']}",
            f"- 편집: {step['edit']}",
            "",
        ])
    export_lines.extend([
        "## 음원 확인",
        f"- 추천 음원: {personalized['track']['곡명']}",
        f"- 권리 상태: {(personalized['track'].get('rights') or {}).get('status', '사용 전 확인 필요')}",
        "",
        "AI 예상과 추천은 게시 후 실제 Instagram 지표로 다시 검증해야 합니다.",
    ])
    st.download_button(
        "촬영·편집 보드 내려받기",
        data="\n".join(export_lines),
        file_name=f"{btype}_reel_production_board.md",
        mime="text/markdown",
        use_container_width=True,
    )

    st.markdown("**캡션 첫 줄 추천**")
    if personalized:
        for caption_text in personalized["captions"]:
            st.code(caption_text, language=None)
    else:
        st.code(f"우리 동네에서 대표 메뉴 찾는다면 저장해두세요.", language=None)


elif menu == "Radar":
    page_header(
        "Radar",
        "내 상권에서 평소보다 빠르게 커지는 콘텐츠를 찾고 다음 제작 프로젝트로 가져옵니다.",
    )

    market_tab, account_tab, operations_tab = st.tabs(["Signals", "Connected account", "System"])

    with account_tab:
        st.subheader("Meta 계정 동기화")
        st.caption("환경 변수 토큰 또는 Meta OAuth 세션을 사용합니다. OAuth 토큰은 현재 앱 세션에만 보관합니다.")

        oauth_ready = all(has_env(name) for name in ["META_APP_ID", "META_APP_SECRET", "META_REDIRECT_URI"])
        if oauth_ready:
            if "meta_oauth_state" not in st.session_state:
                oauth_url, oauth_state = build_oauth_url()
                st.session_state["meta_oauth_url"] = oauth_url
                st.session_state["meta_oauth_state"] = oauth_state
            st.link_button("Instagram 계정 연결", st.session_state["meta_oauth_url"], use_container_width=True)

            query_params = st.query_params
            callback_code = query_params.get("code", "")
            callback_state = query_params.get("state", "")
            if callback_code and not st.session_state.get("meta_access_token"):
                if callback_state != st.session_state.get("meta_oauth_state"):
                    st.error("Meta 로그인 state 값이 일치하지 않습니다. 연결을 다시 시작해주세요.")
                else:
                    try:
                        token_payload = exchange_authorization_code(callback_code)
                        st.session_state["meta_access_token"] = token_payload.get("access_token", "")
                        st.session_state["meta_token_expires_in"] = token_payload.get("expires_in")
                        encryption_key = get_env("META_TOKEN_ENCRYPTION_KEY")
                        if encryption_key and AUTH_USER_ID:
                            save_encrypted_token(
                                st.session_state["meta_access_token"],
                                encryption_key,
                                META_TOKEN_VAULT,
                                {
                                    "expires_in": token_payload.get("expires_in"),
                                    "auth_user_id": AUTH_USER_ID,
                                    "business_type": btype,
                                },
                            )
                        st.query_params.clear()
                        st.success("Instagram 계정 연결이 완료됐습니다.")
                    except Exception as exc:
                        st.error(f"Instagram 로그인 코드 교환 실패: {exc}")
        else:
            st.info("META_APP_ID, META_APP_SECRET, META_REDIRECT_URI를 설정하면 Instagram 로그인 버튼이 활성화됩니다.")

        stored_token = load_encrypted_token(get_env("META_TOKEN_ENCRYPTION_KEY"), META_TOKEN_VAULT)
        active_meta_token = st.session_state.get("meta_access_token") or (stored_token or {}).get("token") or get_env("META_ACCESS_TOKEN")
        if st.session_state.get("meta_access_token"):
            token_source = "OAuth 세션"
        elif stored_token:
            token_source = "암호화 저장"
        else:
            token_source = "환경 변수" if active_meta_token else "연결 안 됨"
        st.caption(f"현재 연결 방식: {token_source}")
        if stored_token and st.button("저장된 Instagram 연결 해제", use_container_width=True):
            delete_encrypted_token(META_TOKEN_VAULT)
            st.session_state.pop("meta_access_token", None)
            st.rerun()
        sync_limit = st.slider("가져올 최근 릴스 수", min_value=5, max_value=50, value=20, step=5)
        if st.button(
            "내 Instagram 릴스 동기화",
            type="primary",
            use_container_width=True,
            disabled=not bool(active_meta_token),
        ):
            try:
                with st.spinner("Meta에서 내 릴스 성과를 가져오는 중입니다..."):
                    payload = collect_my_reels(access_token=active_meta_token, limit=sync_limit)
                    profile = payload["profile"]
                    current_profile = st.session_state.get("store_profile") or {}
                    for reel in payload["reels"]:
                        entry = meta_reel_to_library_entry(
                            reel,
                            btype,
                            profile.get("username", ""),
                            store_id=current_profile.get("store_id", ""),
                        )
                        entry["출처"] = "Meta 실측"
                        upsert_user_reel(entry)
                        append_performance_snapshot(
                            reel.get("id", ""),
                            reel.get("insights", {}),
                            permalink=reel.get("permalink", ""),
                        )
                    cloud_sync = None
                    if has_env("SUPABASE_URL") and has_env("SUPABASE_ANON_KEY"):
                        try:
                            cloud_sync = sync_meta_account(
                                profile,
                                payload["reels"],
                                btype,
                                current_profile,
                                auth_user_id=AUTH_USER_ID,
                            )
                        except Exception as cloud_exc:
                            st.warning(f"로컬 동기화는 완료됐지만 Supabase 저장은 실패했습니다: {cloud_exc}")
                st.cache_data.clear()
                st.session_state["meta_sync_summary"] = {
                    "username": profile.get("username", ""),
                    "count": len(payload["reels"]),
                    "graph_version": payload.get("graph_version", ""),
                    "cloud_sync": cloud_sync,
                }
                st.success(f"@{profile.get('username', '')}의 릴스 {len(payload['reels'])}개를 동기화했습니다.")
            except Exception as exc:
                st.error(f"Meta 동기화 실패: {exc}")

        if not active_meta_token:
            st.info("Instagram 로그인 또는 META_ACCESS_TOKEN 설정 후 동기화할 수 있습니다.")

        measured_reels = [item for item in load_user_reels(btype) if item.get("출처") == "Meta 실측"]
        if measured_reels:
            baseline = build_account_baseline([{"insights": item.get("insights", {})} for item in measured_reels])
            calibration = build_prediction_calibration(measured_reels)
            b1, b2, b3, b4 = st.columns(4)
            b1.metric("실측 릴스", f"{baseline['count']}개")
            b2.metric("중앙 조회수", f"{int(baseline['median_views']):,}")
            b3.metric("중앙 참여율", f"{baseline['median_engagement_rate']:.2f}%")
            b4.metric("예측 보정 표본", f"{calibration['sample_count']}개")
            if calibration.get("mae") is not None:
                st.caption(
                    f"내 계정 보정: AI 점수 편향 {calibration['bias']:+.1f}점 · "
                    f"보정 후 평균 오차 {calibration['mae']:.1f}점 · "
                    f"80% 오차 범위 ±{calibration.get('error_interval_80', 0):.1f}점 · "
                    f"신뢰도 {calibration['confidence']}"
                )

            st.markdown("**게시 전 예상과 게시 후 실측 비교**")
            comparisons = []
            for item in measured_reels:
                comparison = compare_prediction_to_actual(item.get("analysis"), item.get("insights"), calibration)
                history_delta = compare_measured_snapshots(load_performance_history(item.get("instagram_media_id") or item.get("릴스")))
                comparisons.append({
                    "릴스": item.get("릴스명"),
                    "AI 예상": comparison["predicted_score"],
                    "Meta 실측": comparison["actual_score"],
                    "차이": comparison["delta"],
                    "판정": comparison["verdict"],
                    "최근 조회 증가": history_delta["views_delta"] if history_delta else None,
                    "최근 저장 증가": history_delta["saved_delta"] if history_delta else None,
                    "링크": item.get("링크"),
                })
            st.dataframe(
                pd.DataFrame(comparisons),
                use_container_width=True,
                hide_index=True,
                column_config={"링크": st.column_config.LinkColumn("원본", display_text="열기")},
            )
            if not any(item.get("analysis") for item in measured_reels):
                st.info("동기화된 릴스의 로컬 영상을 분석하면 AI 예상과 Meta 실측 비교가 채워집니다.")
        else:
            st.info("아직 Meta 실측 릴스가 없습니다. 계정을 동기화하면 기준선과 비교표가 표시됩니다.")

        if AUTH_USER_ID:
            with st.expander("내 데이터 내보내기·삭제"):
                st.caption("로컬 분석 자료를 ZIP으로 내려받거나 삭제할 수 있습니다. Supabase 계정 삭제는 운영 관리자 확인이 추가로 필요합니다.")
                if st.button("내 데이터 내보내기 준비", use_container_width=True):
                    try:
                        archive = export_user_data(AUTH_USER_ID)
                        st.session_state["privacy_export_path"] = str(archive)
                    except FileNotFoundError as exc:
                        st.info(str(exc))
                export_path = Path(st.session_state.get("privacy_export_path", ""))
                if export_path.is_file():
                    st.download_button(
                        "ZIP 다운로드",
                        data=export_path.read_bytes(),
                        file_name=export_path.name,
                        mime="application/zip",
                        use_container_width=True,
                    )
                delete_confirmation = st.text_input("삭제하려면 DELETE 입력", key="delete_local_data_confirmation")
                if st.button(
                    "내 로컬 데이터 삭제",
                    disabled=delete_confirmation != "DELETE",
                    use_container_width=True,
                ):
                    deleted = delete_user_data(AUTH_USER_ID, dry_run=False)
                    st.session_state.pop("store_profile", None)
                    st.session_state.pop("latest_analysis", None)
                    st.success(f"로컬 파일 {len(deleted)}개를 삭제했습니다.")

                st.divider()
                cloud_delete_confirmation = st.text_input(
                    "계정까지 삭제하려면 DELETE ACCOUNT 입력",
                    key="delete_cloud_account_confirmation",
                )
                if st.button(
                    "계정과 모든 연결 데이터 삭제",
                    disabled=(
                        cloud_delete_confirmation != "DELETE ACCOUNT"
                        or not has_env("SUPABASE_SERVICE_ROLE_KEY")
                    ),
                    use_container_width=True,
                ):
                    try:
                        delete_cloud_account(AUTH_USER_ID)
                        delete_user_data(AUTH_USER_ID, dry_run=False)
                        for key in ["app_auth", "store_profile", "latest_analysis", "meta_access_token"]:
                            st.session_state.pop(key, None)
                        st.success("계정과 연결 데이터를 삭제했습니다.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"계정 삭제 실패: {exc}")
                if not has_env("SUPABASE_SERVICE_ROLE_KEY"):
                    st.caption("SUPABASE_SERVICE_ROLE_KEY를 서버에 설정하면 계정 전체 삭제가 활성화됩니다.")

    with market_tab:
        st.subheader("지역·업종 주간 추적")
        default_place = (st.session_state.get("store_profile") or {}).get("place", "성수동")
        market_place = st.text_input("지역/상권", value=default_place, placeholder="예: 성수동, 홍대입구역")
        market_query = f"{market_place.strip()}{btype}" if market_place.strip() else btype
        market_count = st.slider("분석할 공개 릴스 수", min_value=5, max_value=30, value=15, step=5)
        alert_cols = st.columns([1, 1])
        alerts_enabled = alert_cols[0].toggle("주간 변화 알림", value=True)
        alert_min_views = alert_cols[1].number_input(
            "알림 기준 조회 증가",
            min_value=1000,
            max_value=10_000_000,
            value=10000,
            step=1000,
            disabled=not alerts_enabled,
        )
        watch_cols = st.columns([2, 1])
        if watch_cols[1].button("주간 추적 목록에 저장", use_container_width=True, disabled=not market_place.strip()):
            watches = save_watch(
                market_query,
                btype,
                market_place.strip(),
                market_count,
                path=MARKET_WATCHLIST_PATH,
                alerts_enabled=alerts_enabled,
                min_views=int(alert_min_views),
            )
            st.success(f"주간 추적 목록에 저장했습니다. 현재 {len(watches)}개 검색어를 추적합니다.")
        watches = load_watchlist(MARKET_WATCHLIST_PATH)
        if watches:
            watch_cols[0].caption("추적 중: " + ", ".join(item["query"] for item in watches))

        if st.button(
            "현재 시장 스냅샷 수집",
            type="primary",
            use_container_width=True,
            disabled=not has_env("APIFY_TOKEN") or not market_place.strip(),
        ):
            try:
                with st.spinner(f"{market_query} 공개 릴스를 수집하는 중입니다..."):
                    reels = collect_top_reels(
                        market_query,
                        max_items=max(market_count * 3, 30),
                        top_n=market_count,
                    )
                    previous = load_previous_snapshot(market_query, base_dir=MARKET_SNAPSHOT_DIR)
                    snapshot = build_market_snapshot(reels, market_query)
                    changes = compare_snapshots(previous, snapshot)
                    alerts = build_market_alerts(previous, snapshot)
                    path = save_snapshot(snapshot, base_dir=MARKET_SNAPSHOT_DIR)
                    st.session_state["market_snapshot"] = snapshot
                    st.session_state["market_changes"] = changes
                    st.session_state["market_snapshot_path"] = str(path)
                    st.session_state["market_alerts"] = alerts
                st.success(f"{snapshot['reel_count']}개 릴스로 시장 스냅샷을 저장했습니다.")
            except Exception as exc:
                st.error(f"시장 스냅샷 수집 실패: {exc}")

        if not has_env("APIFY_TOKEN"):
            st.info(".env에 APIFY_TOKEN을 설정하면 공개 릴스 추적을 실행할 수 있습니다.")

        snapshot = st.session_state.get("market_snapshot")
        changes = st.session_state.get("market_changes", [])
        alerts = st.session_state.get("market_alerts", [])
        if snapshot and snapshot.get("query") == market_query:
            m1, m2, m3 = st.columns(3)
            m1.metric("분석 릴스", f"{snapshot['reel_count']}개")
            m2.metric("발견 계정", f"{len(snapshot['accounts'])}개")
            m3.metric("새 계정", f"{sum(1 for item in changes if item.get('is_new'))}개")
            if changes:
                st.dataframe(
                    pd.DataFrame(changes)[[
                        "username", "reel_count", "views", "same_media_view_delta", "same_media_count",
                        "comparison_confidence", "likes", "shares", "top_reel"
                    ]],
                    use_container_width=True,
                    hide_index=True,
                    column_config={"top_reel": st.column_config.LinkColumn("대표 릴스", display_text="열기")},
                )
                project_candidates = [item for item in changes if item.get("top_reel")]
                if project_candidates:
                    selected_signal = st.selectbox(
                        "Studio로 가져올 경쟁 신호",
                        range(len(project_candidates)),
                        format_func=lambda index: (
                            f"@{project_candidates[index]['username']} · "
                            f"조회 {int(project_candidates[index].get('views') or 0):,}"
                        ),
                    )
                    signal = project_candidates[selected_signal]
                    if st.button("Create project from signal", type="primary", use_container_width=True):
                        project = create_project(
                            f"@{signal['username']} 패턴 각색",
                            CONTENT_PROJECTS_PATH,
                            business_type=btype,
                            concept="경쟁 콘텐츠의 구조를 내 매장에 맞게 각색",
                            source={
                                "type": "competitor_signal",
                                "username": signal.get("username", ""),
                                "url": signal.get("top_reel", ""),
                                "views": signal.get("views", 0),
                                "view_delta": signal.get("same_media_view_delta", 0),
                                "query": market_query,
                            },
                        )
                        st.session_state["active_project_id"] = project["id"]
                        go_to_menu("Studio")
            else:
                st.info("비교할 계정 데이터가 없습니다.")
            if alerts:
                st.markdown("**변화 알림**")
                for alert in alerts:
                    st.warning(f"@{alert['username']} · {alert['message']}")
                    if alert.get("url"):
                        st.markdown(f"[알림 릴스 열기]({alert['url']})")
            elif changes:
                st.info("설정한 기준을 넘는 급상승 릴스는 없습니다.")
            if snapshot.get("top_hashtags"):
                st.markdown("**이번 스냅샷 상위 해시태그**")
                st.code(" ".join(snapshot["top_hashtags"]), language=None)
            if snapshot.get("top_tracks"):
                st.markdown("**이번 스냅샷에서 확인된 음원**")
                st.write(", ".join(snapshot["top_tracks"]))
            st.caption(f"저장 위치: {st.session_state.get('market_snapshot_path', '')}")

        delivery_history = load_jsonl_history(MARKET_DELIVERY_HISTORY, limit=10)
        if delivery_history:
            with st.expander("최근 알림 전송 이력"):
                st.dataframe(pd.DataFrame(delivery_history), use_container_width=True, hide_index=True)

    with operations_tab:
        st.subheader("서비스 운영 현황")
        st.caption("오늘의 외부 API 사용량과 분석 작업 상태, 최근 실패를 한 화면에서 확인합니다.")
        gemini_usage = get_daily_usage("gemini")
        apify_usage = get_daily_usage("apify")
        meta_usage = get_daily_usage("meta")
        operation_jobs = list_jobs(limit=100, owner_id=JOB_OWNER_ID, path=JOB_DB_PATH)
        running_jobs = sum(1 for item in operation_jobs if item.get("status") == "running")
        failed_jobs = sum(1 for item in operation_jobs if item.get("status") == "failed")
        oc1, oc2, oc3, oc4 = st.columns(4)
        oc1.metric("Gemini 호출", f"{gemini_usage['calls']}회", f"${gemini_usage['estimated_cost_usd']:.4f}")
        oc2.metric("Apify 호출", f"{apify_usage['calls']}회", f"${apify_usage['estimated_cost_usd']:.4f}")
        oc3.metric("Meta 동기화", f"{meta_usage['calls']}회")
        oc4.metric("실행/실패 작업", f"{running_jobs}/{failed_jobs}")

        recent_failures = load_recent_events(limit=25, failures_only=True)
        if recent_failures:
            st.markdown("**최근 처리 실패**")
            st.dataframe(pd.DataFrame(recent_failures), use_container_width=True, hide_index=True)
        else:
            st.success("기록된 최근 처리 실패가 없습니다.")

        if operation_jobs:
            st.markdown("**최근 분석 작업**")
            job_rows = [{
                "작업 ID": item.get("id", "")[:8],
                "종류": item.get("kind", ""),
                "상태": item.get("status", ""),
                "진행률": item.get("progress", 0),
                "시도": f"{item.get('attempts', 0)}/{item.get('max_attempts', 0)}",
                "갱신": item.get("updated_at", ""),
                "오류": item.get("error", ""),
            } for item in operation_jobs[:25]]
            st.dataframe(pd.DataFrame(job_rows), use_container_width=True, hide_index=True)
