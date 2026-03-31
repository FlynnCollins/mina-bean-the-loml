# Splunk Fuzzy Match Command - Installation & Configuration Guide

## Quick Start

### 1. Create the App Structure

```bash
mkdir -p $SPLUNK_HOME/etc/apps/fuzzy_match/bin
mkdir -p $SPLUNK_HOME/etc/apps/fuzzy_match/default
mkdir -p $SPLUNK_HOME/etc/apps/fuzzy_match/docs
```

### 2. Install Dependencies

```bash
# Add to $SPLUNK_HOME/etc/apps/fuzzy_match/default/requirements.txt
rapidfuzz>=3.0.0
```

Install via Splunk's Python environment:

```bash
$SPLUNK_HOME/bin/splunk cmd python -m pip install -r $SPLUNK_HOME/etc/apps/fuzzy_match/default/requirements.txt
```

### 3. Deploy Command File

Copy `fuzzymatch.py` to `$SPLUNK_HOME/etc/apps/fuzzy_match/bin/`

### 4. Register Command in commands.conf

**File:** `$SPLUNK_HOME/etc/apps/fuzzy_match/default/commands.conf`

```ini
[fuzzymatch]
filename = fuzzymatch.py
is_streaming = true
python.version = python3
requires_preop = false
output_as_tsv = true
```

---

## Configuration Examples

### Basic Configuration (Single Record Matching)

**Scenario:** Match user input against a reference field

```spl
sourcetype=support_tickets
| fuzzymatch field=reported_issue match_field=known_issue_title 
    algorithm=token_set 
    threshold=85 
    output_field=matched_issue 
    output_score=issue_confidence
```

**Command Breakdown:**
- `field=reported_issue` → Input from user (potentially misspelled)
- `match_field=known_issue_title` → Reference database field
- `algorithm=token_set` → Handles word order differences
- `threshold=85` → Only match if 85+ similarity
- `output_field=matched_issue` → Store best match here
- `output_score=issue_confidence` → Store score (0-100) here


### Static Choices Configuration

**Scenario:** Normalize free-text severity field to standard values

```spl
source=application_logs
| fuzzymatch field=severity_text 
    choices="CRITICAL,HIGH,MEDIUM,LOW,INFO,DEBUG" 
    algorithm=partial_ratio 
    threshold=70 
    processor=uppercase 
    output_field=normalized_severity
```

**Use Case:** Application logs may have variations like "CRIT", "CRITICAL", "Crit" that need standardization


### Multi-Value Field Matching

**Scenario:** Match against multiple candidates from a lookup table

```spl
source=transactions
| lookup product_lookup output_product_names
| fuzzymatch field=user_input_product 
    choices_from_field=output_product_names 
    algorithm=token_sort 
    threshold=75 
    processor=alphanumeric 
    output_field=identified_product 
    output_score=product_match_confidence
```

**Workflow:**
1. `lookup` enriches with comma-separated product list
2. `fuzzymatch` finds best match from that list
3. Scores saved for downstream filtering/logging


### Address Matching

**Scenario:** Match customer addresses with slight variations

```spl
source=crm_data
| fuzzymatch field=customer_address 
    match_field=canonical_address 
    algorithm=token_set 
    processor=alphanumeric 
    threshold=90 
    case_sensitive=false 
    output_score=address_match_score
| where address_match_score >= 90
```

**Why this config:**
- `token_set` → Handles word order: "123 Main St, NY" vs "NY 123 Main Street"
- `alphanumeric` → Removes punctuation: "St." vs "Street"
- `threshold=90` → Strict for address data
- Filter on threshold again for extra certainty


### Typo Tolerance (Names)

**Scenario:** Detect typos in customer names

```spl
source=customer_signups
| fuzzymatch field=entered_name 
    match_field=verified_name 
    algorithm=jaro_winkler 
    threshold=85 
    processor=default 
    output_score=name_similarity
| stats count, values(entered_name) by verified_name, name_similarity
```

**Why Jaro-Winkler:**
- Optimized for short strings (names)
- Weights matching prefixes highly
- Good for common typos: "Jon" vs "John"


### Case-Sensitive Matching (IDs/Codes)

**Scenario:** Match API tokens or case-sensitive codes

```spl
source=api_logs
| fuzzymatch field=provided_token 
    match_field=valid_token 
    algorithm=distance 
    threshold=95 
    case_sensitive=true 
    processor=none 
    output_score=token_distance
| where token_distance >= 95
```

**Why this config:**
- `distance` → Character-level edit distance
- `case_sensitive=true` → Respect capitalization
- `processor=none` → No preprocessing
- `threshold=95` → Very strict (tokens are mission-critical)


### Performance-Optimized (Large Lookup)

**Scenario:** Matching against thousands of products with focus on speed

```spl
source=user_searches
| fuzzymatch field=search_term 
    choices_from_field=all_product_names 
    algorithm=partial_ratio 
    threshold=70 
    processor=lowercase 
    output_field=suggested_product 
    output_score=relevance
| where relevance > 70
| stats count by suggested_product, relevance
```

**Optimizations:**
- `partial_ratio` → Faster for large datasets (one-to-many)
- `processor=lowercase` → Simple preprocessing, good performance
- `threshold=70` → Lenient to get results quickly
- Filter afterwards to refine results


---

## Advanced Usage Patterns

### Chained Fuzzy Matching

Two-stage matching: first coarse, then fine-grained

```spl
source=ticket_system
| fuzzymatch field=user_reported_category 
    choices="infrastructure,database,application,network,security" 
    algorithm=simple_ratio 
    threshold=60 
    output_field=category_group

| lookup category_details category_group output_subcategories
| fuzzymatch field=user_issue 
    choices_from_field=output_subcategories 
    algorithm=token_sort 
    threshold=80 
    output_field=matched_subcategory 
    output_score=sub_confidence
```

**Workflow:**
1. First fuzzymatch narrows to category (lenient, 60%)
2. Lookup finds relevant subcategories
3. Second fuzzymatch picks best subcategory (strict, 80%)


### Fuzzy Matching with Eval

Create composite scoring:

```spl
source=customer_data
| fuzzymatch field=query_name 
    match_field=crm_name 
    algorithm=token_set 
    threshold=50 
    output_score=name_score

| fuzzymatch field=query_email 
    match_field=crm_email 
    algorithm=distance 
    processor=alphanumeric 
    output_score=email_score

| eval combined_score = (name_score + email_score) / 2
| stats values(crm_name), values(crm_email) by query_name, query_email, combined_score
| where combined_score >= 85
```

**Power:** Combine multiple fuzzy scores for stronger matching


### Fuzzy Deduplication

Find near-duplicate records:

```spl
source=raw_imports
| fuzzymatch field=product_name 
    match_field=product_name 
    algorithm=token_sort 
    threshold=95 
    output_score=dup_score
| stats count, values(_raw) by product_name, dup_score
| where count > 1 AND dup_score > 95
```

**Result:** Identify records that are 95%+ similar (likely duplicates)


---

## Performance Tuning

### By Scenario

| Scenario | Optimization | Config |
|----------|--------------|--------|
| **Large lookup (1000+ items)** | Use `partial_ratio`, lenient threshold | `algorithm=partial_ratio threshold=70` |
| **Real-time indexing** | Use `simple_ratio`, limit candidates | `algorithm=simple_ratio processor=default` |
| **Batch processing** | Use strict algorithm | `algorithm=token_set threshold=90` |
| **Interactive dashboards** | Pre-process data in saved search | Use eval to precompute matches |
| **Memory-constrained** | Avoid `choices_from_field` with huge lists | Chunk data or use staged lookups |

### Configuration Tips

1. **Processor Impact:** `none` > `lowercase` > `default` > `alphanumeric` (speed-wise)
   - Use `none` or `lowercase` for performance
   - Use `alphanumeric` only when needed (punctuation matters)

2. **Algorithm Impact (slowest to fastest):**
   - Slowest: `token_set` (most accurate)
   - Mid: `token_sort`, `distance`
   - Fastest: `partial_ratio`, `simple_ratio`

3. **Threshold Impact:** Higher threshold = faster (fewer comparisons needed)

4. **Scale:** For 1000+ candidates, consider:
   ```spl
   | stats count by field | fuzzymatch ... | stats sum(count)
   ```
   (Aggregate first, then match once per group)


### Resource Monitoring

Add to `props.conf` if tracking performance:

```ini
[fuzzy_match_perf]
FIELDALIAS-duration = duration AS fuzzy_match_duration_ms
```

Monitor in Splunk:

```spl
index=_internal group=fuzzymatch
| stats avg(duration) max(duration) by sourcetype, algorithm
```


---

## Troubleshooting

### Command Not Found

```
Error in 'fuzzymatch': Could not find command 'fuzzymatch'
```

**Solutions:**
1. Verify file is in correct location: `$SPLUNK_HOME/etc/apps/fuzzy_match/bin/fuzzymatch.py`
2. Check `commands.conf` syntax
3. Restart Splunk: `$SPLUNK_HOME/bin/splunk restart`
4. Check permissions: `chmod 755 fuzzymatch.py`


### Import Error: "No module named 'rapidfuzz'"

```
Error in 'fuzzymatch': Python exception: No module named 'rapidfuzz'
```

**Solutions:**
1. Install package:
   ```bash
   $SPLUNK_HOME/bin/splunk cmd python -m pip install rapidfuzz
   ```
2. Verify installation:
   ```bash
   $SPLUNK_HOME/bin/splunk cmd python -c "import rapidfuzz; print(rapidfuzz.__version__)"
   ```
3. Check Python version compatibility (Python 3.6+)


### All Scores Are 0

**Causes & Solutions:**
- Field doesn't exist: Check field names with `fields` command
- Empty values: Use `where fieldname != ""`
- Wrong processor: Check case sensitivity expectations

```spl
| fuzzymatch field=input match_field=reference algorithm=token_set
| where fuzzy_score > 0
```


### Threshold Too High / Too Low

**Symptoms:**
- Everything matches (threshold too low): Lower it gradually
- Nothing matches (threshold too high): Raise it gradually

**Debug:**
```spl
| fuzzymatch field=input match_field=reference algorithm=token_set
| stats count by fuzzy_score
| chart count by fuzzy_score
```

This shows score distribution; adjust threshold to inflection point.


---

## Best Practices

1. **Always include output_score** for monitoring and troubleshooting
2. **Filter on threshold twice**: Once in command args, once with `where`
3. **Test with sample data first** before deploying to production searches
4. **Use descriptive field names** for output (`matched_product`, not `match`)
5. **Version your choice lists** if they come from lookups
6. **Monitor performance** on high-volume searches
7. **Document algorithm choices** in search comments:
   ```spl
   | fuzzymatch field=name match_field=ref_name algorithm=token_set threshold=85
   # token_set used for order-independent matching of names
   # threshold=85 allows for minor typos but prevents false positives
   ```


---

## Example: Production-Ready Search

```spl
# Normalize messy product input to catalog
index=web_events event_type=product_search
| rename search_term AS user_input
| lookup product_catalog output_canonical_names
| fuzzymatch field=user_input 
    choices_from_field=output_canonical_names 
    algorithm=token_sort 
    processor=alphanumeric 
    threshold=75 
    output_field=matched_product 
    output_score=match_confidence
| where match_confidence >= 75
| eval product_matched = if(match_confidence >= 90, "HIGH", if(match_confidence >= 75, "MEDIUM", "LOW"))
| stats count, latest(match_confidence) as avg_confidence by matched_product, product_matched
| sort - count
```

**Why this works:**
- Lookup enriches with valid products
- `token_sort` handles varied wording
- `alphanumeric` removes punctuation noise
- Two thresholds: in-command (75) and where clause (redundancy)
- Confidence categorization for reporting
- Stats summarizes effectiveness