# Graph Report - CALL_RECORDS  (2026-04-22)

## Corpus Check
- 40 files · ~43,370 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 280 nodes · 649 edges · 11 communities detected
- Extraction: 70% EXTRACTED · 30% INFERRED · 0% AMBIGUOUS · INFERRED: 196 edges (avg confidence: 0.6)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]

## God Nodes (most connected - your core abstractions)
1. `run_ingest()` - 29 edges
2. `_exclude_whatsapp_clause()` - 19 edges
3. `request()` - 18 edges
4. `HumanReviewFeedback` - 15 edges
5. `ReviewUpdatePayload` - 15 edges
6. `TranscriptReview` - 15 edges
7. `Apply aggressive uplift (profile 3) while preserving the 1-5 scale.` - 14 edges
8. `Export the full table as CSV. Uses a streaming response to avoid large memory us` - 14 edges
9. `Return sentiment distribution (positive/neutral/negative) for each parent psycho` - 14 edges
10. `Simple global search across transcripts and sentiment text fields.      Return` - 14 edges

## Surprising Connections (you probably didn't know these)
- `get_trend()` --calls--> `TrendPoint`  [INFERRED]
  backend\app\api\routes_dashboard.py → backend\app\schemas\dashboard.py
- `get_distribution()` --calls--> `DistributionPoint`  [INFERRED]
  backend\app\api\routes_dashboard.py → backend\app\schemas\dashboard.py
- `get_intent_distribution()` --calls--> `DistributionPoint`  [INFERRED]
  backend\app\api\routes_dashboard.py → backend\app\schemas\dashboard.py
- `get_calls()` --calls--> `CallItem`  [INFERRED]
  backend\app\api\routes_dashboard.py → backend\app\schemas\dashboard.py
- `get_call_detail()` --calls--> `CallDetail`  [INFERRED]
  backend\app\api\routes_dashboard.py → backend\app\schemas\dashboard.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.09
Nodes (59): RuntimeError, _build_gemini_transcription_prompt(), _build_recognition_config(), _build_speaker_labeling_prompt(), _build_speech_preprocess_filter(), can_normalize_audio_locally(), _cleanup_labeled_transcript(), _contains_language_tags() (+51 more)

### Community 1 - "Community 1"
Cohesion: 0.09
Nodes (39): download_file_bytes(), _audio_media_type_for_file_name(), _blend_toward_optimistic(), _boost_staff_metric(), _build_detailed_call_insight(), _exclude_whatsapp_clause(), export_db_table(), _extract_phone_from_file_name() (+31 more)

### Community 2 - "Community 2"
Cohesion: 0.1
Nodes (33): download_text_file(), DriveFile, _escape_drive_query_value(), list_audio_files(), _list_drive_files(), list_txt_files(), resolve_folder_id_from_path(), resolve_drive_folder_id() (+25 more)

### Community 3 - "Community 3"
Cohesion: 0.33
Nodes (27): Base, Base, BaseModel, CallDetail, CallItem, CallsByNumberItem, DailyOverallKPITrend, DistributionPoint (+19 more)

### Community 4 - "Community 4"
Cohesion: 0.16
Nodes (19): getCallAudioUrl(), getCallDetail(), getCalls(), getCallsByNumber(), getDbTableRows(), getDbTables(), getDistribution(), getGoogleAuthUrl() (+11 more)

### Community 5 - "Community 5"
Cohesion: 0.17
Nodes (14): _auto_ingest_loop(), _is_invalid_grant_error(), start_auto_ingest_thread(), begin_ingest(), _default_progress(), fail_ingest(), finish_ingest(), get_ingest_status() (+6 more)

### Community 6 - "Community 6"
Cohesion: 0.21
Nodes (6): BaseSettings, parse_allowed_transcript_languages(), parse_cors_origins(), parse_google_speech_language_codes(), _parse_string_list(), Settings

### Community 7 - "Community 7"
Cohesion: 0.42
Nodes (8): _build_classifier_prompt(), classify_intent_summary(), _classify_with_gemini(), _classify_with_openai(), _clean_summary(), _is_likely_english(), _normalize_intent(), _parse_classifier_output()

### Community 8 - "Community 8"
Cohesion: 0.6
Nodes (5): _client(), test_dashboard_smoke_endpoints_return_200(), test_google_auth_url_endpoint_responds(), test_health_endpoint_returns_ok(), test_ingest_status_endpoint_returns_shape()

### Community 9 - "Community 9"
Cohesion: 0.7
Nodes (4): Get-ListeningPids(), Show-PortStatus(), Stop-ListeningProcesses(), Wait-PortReady()

### Community 10 - "Community 10"
Cohesion: 0.7
Nodes (4): fetch_unreviewed_transcripts(), main(), review_transcript(), update_transcript_review()

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `run_ingest()` connect `Community 2` to `Community 0`, `Community 1`, `Community 3`, `Community 5`, `Community 7`?**
  _High betweenness centrality (0.330) - this node is a cross-community bridge._
- **Why does `get_google_access_token()` connect `Community 2` to `Community 0`, `Community 1`?**
  _High betweenness centrality (0.178) - this node is a cross-community bridge._
- **Why does `get_call_audio()` connect `Community 1` to `Community 2`?**
  _High betweenness centrality (0.121) - this node is a cross-community bridge._
- **Are the 20 inferred relationships involving `run_ingest()` (e.g. with `ingest_now()` and `_auto_ingest_loop()`) actually correct?**
  _`run_ingest()` has 20 INFERRED edges - model-reasoned connections that need verification._
- **Are the 13 inferred relationships involving `HumanReviewFeedback` (e.g. with `Transcript` and `Sentiment`) actually correct?**
  _`HumanReviewFeedback` has 13 INFERRED edges - model-reasoned connections that need verification._
- **Are the 13 inferred relationships involving `ReviewUpdatePayload` (e.g. with `Transcript` and `Sentiment`) actually correct?**
  _`ReviewUpdatePayload` has 13 INFERRED edges - model-reasoned connections that need verification._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.09 - nodes in this community are weakly interconnected._