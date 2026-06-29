#!/usr/bin/env bash
#
# Extreme Load Test Runner for Rivex
# Tests all server packages progressively up to 1B requests / 10K concurrency
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
RESULTS_DIR="$SCRIPT_DIR/results/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RESULTS_DIR"

# ── Colors ──
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log()  { echo -e "${CYAN}[$(date +%H:%M:%S)]${NC} $*"; }
ok()   { echo -e "${GREEN}[OK]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
fail() { echo -e "${RED}[FAIL]${NC} $*"; }
header() { echo -e "\n${BOLD}═══════════════════════════════════════════════════${NC}"; echo -e "${BOLD} $*${NC}"; echo -e "${BOLD}═══════════════════════════════════════════════════${NC}\n"; }

# ── System tuning ──
tune_system() {
    log "Tuning system limits..."
    ulimit -n 65536 2>/dev/null || warn "Could not raise file descriptor limit (need sudo)"
    # macOS: ensure enough ephemeral ports
    if [[ "$(uname)" == "Darwin" ]]; then
        log "macOS detected — ephemeral port range: $(sysctl -n net.inet.ip.portrange.first)-$(sysctl -n net.inet.ip.portrange.last)"
    fi
    log "File descriptor limit: $(ulimit -n)"
}

# ── Server lifecycle ──
start_server() {
    local name="$1" module="$2" port="$3"
    shift 3
    log "Starting $name on port $port..."
    cd "$PROJECT_DIR"
    if [[ "$module" == *"asgi"* ]]; then
        # ASGI via uvicorn
        python3 -m uvicorn "$module" --host 0.0.0.0 --port "$port" --workers "${1:-1}" \
            --log-level error --no-access-log &
    else
        python3 -m "$module" "$port" "${1:-1}" &
    fi
    SERVER_PID=$!
    # Wait for server to be ready
    for i in $(seq 1 30); do
        if curl -sf "http://127.0.0.1:$port/ping" > /dev/null 2>&1; then
            ok "$name ready (PID=$SERVER_PID)"
            return 0
        fi
        sleep 0.5
    done
    fail "$name failed to start"
    kill $SERVER_PID 2>/dev/null || true
    return 1
}

stop_server() {
    if [[ -n "${SERVER_PID:-}" ]]; then
        log "Stopping server (PID=$SERVER_PID)..."
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
        unset SERVER_PID
        sleep 1
    fi
}

trap 'stop_server; echo; log "Cleanup complete."' EXIT

# ── Benchmark runners ──

run_wrk() {
    local label="$1" url="$2" conc="$3" duration="$4" outfile="$5"
    shift 5
    local threads=$((conc > 8 ? 8 : conc))
    log "  wrk: $label — ${conc}c × ${duration}s → $url"
    wrk -t"$threads" -c"$conc" -d"${duration}s" "$@" "$url" 2>&1 | tee "$outfile"
    echo "" >> "$outfile"
}

run_hey() {
    local label="$1" url="$2" total="$3" conc="$4" outfile="$5"
    shift 5
    log "  hey: $label — ${total} req @ ${conc}c → $url"
    hey -n "$total" -c "$conc" -t 30 "$@" "$url" 2>&1 | tee "$outfile"
    echo "" >> "$outfile"
}

run_vegeta() {
    local label="$1" url="$2" rate="$3" duration="$4" outfile="$5"
    log "  vegeta: $label — ${rate}/s × ${duration}s → $url"
    echo "GET $url" | vegeta attack -rate="$rate" -duration="${duration}s" -timeout=30s \
        | vegeta report -type=text 2>&1 | tee "$outfile"
    echo "" >> "$outfile"
}

# ── Test tiers ──

TIERS=(
    # label:concurrency:duration_seconds:total_requests(for hey)
    "warmup:100:10:10000"
    "moderate:500:30:500000"
    "heavy:1000:60:5000000"
    "extreme:2500:120:50000000"
    "ultra:5000:180:200000000"
    "max:10000:300:1000000000"
)

run_endpoint_tiers() {
    local server_name="$1" port="$2" endpoint="$3" endpoint_label="$4"
    shift 4
    local url="http://127.0.0.1:$port$endpoint"
    local dir="$RESULTS_DIR/${server_name}/${endpoint_label}"
    mkdir -p "$dir"

    for tier_spec in "${TIERS[@]}"; do
        IFS=':' read -r tier_name conc duration total <<< "$tier_spec"
        header "$server_name / $endpoint_label / TIER: $tier_name (${conc}c)"

        # wrk for sustained throughput
        run_wrk "$tier_name" "$url" "$conc" "$duration" \
            "$dir/wrk_${tier_name}.txt" "$@"

        # Extract requests/sec from wrk output
        local rps
        rps=$(grep "Requests/sec" "$dir/wrk_${tier_name}.txt" | awk '{print $2}' || echo "0")
        log "  → Throughput: $rps req/s"

        # Check for errors
        local errors
        errors=$(grep -c "Socket errors\|Non-2xx" "$dir/wrk_${tier_name}.txt" || echo "0")
        if [[ "$errors" -gt 0 ]]; then
            warn "  → Errors detected at ${conc}c — check $dir/wrk_${tier_name}.txt"
        fi

        # Small cooldown between tiers
        sleep 2
    done
}

run_post_tiers() {
    local server_name="$1" port="$2"
    local url="http://127.0.0.1:$port/items"
    local dir="$RESULTS_DIR/${server_name}/post_items"
    mkdir -p "$dir"

    for tier_spec in "${TIERS[@]}"; do
        IFS=':' read -r tier_name conc duration total <<< "$tier_spec"
        header "$server_name / POST /items / TIER: $tier_name (${conc}c)"
        run_wrk "$tier_name" "$url" "$conc" "$duration" \
            "$dir/wrk_${tier_name}.txt" \
            -s "$SCRIPT_DIR/wrk_post.lua"
        sleep 2
    done
}

# ── Sustained 1B request test (vegeta) ──
run_billion_test() {
    local server_name="$1" port="$2"
    local url="http://127.0.0.1:$port/ping"
    local dir="$RESULTS_DIR/${server_name}/billion"
    mkdir -p "$dir"

    header "$server_name / BILLION REQUEST TEST"
    log "Finding max sustainable rate..."

    # Find max rate with vegeta (quick probes)
    local max_rate=0
    for rate in 5000 10000 25000 50000 75000 100000; do
        log "  Probing ${rate}/s for 10s..."
        local probe_result
        probe_result=$(echo "GET $url" | vegeta attack -rate="$rate" -duration="10s" -timeout=10s \
            | vegeta report -type=text 2>&1)
        local success_pct
        success_pct=$(echo "$probe_result" | grep "Success" | head -1 | awk '{print $NF}' | tr -d '%')
        log "  → Success: ${success_pct}%"
        if (( $(echo "$success_pct > 99.0" | bc -l 2>/dev/null || echo 0) )); then
            max_rate=$rate
        else
            break
        fi
        sleep 1
    done

    if [[ "$max_rate" -eq 0 ]]; then
        max_rate=5000
    fi

    # Calculate duration for 1B requests at max rate
    local billion_duration=$((1000000000 / max_rate))
    log "Max sustainable rate: ${max_rate}/s"
    log "Time for 1B requests at this rate: ${billion_duration}s (~$((billion_duration / 3600))h)"

    # Run a representative long-duration test (cap at 5 minutes for practical reasons)
    local actual_duration=$((billion_duration > 300 ? 300 : billion_duration))
    local actual_requests=$((max_rate * actual_duration))
    log "Running ${actual_duration}s sustained test (${actual_requests} total requests)..."

    echo "GET $url" | vegeta attack -rate="$max_rate" -duration="${actual_duration}s" -timeout=30s \
        | vegeta report -type=text 2>&1 | tee "$dir/sustained.txt"

    # Also capture histogram
    echo "GET $url" | vegeta attack -rate="$max_rate" -duration="60s" -timeout=30s \
        | vegeta report -type='hist[0,1ms,5ms,10ms,25ms,50ms,100ms,250ms,500ms,1s,5s]' \
        2>&1 | tee "$dir/histogram.txt"

    # Write extrapolation
    local actual_rps
    actual_rps=$(grep "Throughput" "$dir/sustained.txt" | awk '{print $2}' || echo "$max_rate")
    local time_for_billion
    time_for_billion=$(echo "1000000000 / $actual_rps" | bc -l 2>/dev/null | cut -d. -f1 || echo "N/A")
    {
        echo "═══ BILLION REQUEST EXTRAPOLATION ═══"
        echo "Sustained RPS: $actual_rps"
        echo "Estimated time for 1B requests: ${time_for_billion}s (~$((time_for_billion / 3600))h $((time_for_billion % 3600 / 60))m)"
        echo "Requests completed in test: $actual_requests"
        echo "Test duration: ${actual_duration}s"
    } | tee "$dir/extrapolation.txt"
}

# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

header "RIVEX EXTREME LOAD TEST SUITE"
log "Results directory: $RESULTS_DIR"
log "Machine: $(uname -m) / $(sysctl -n hw.ncpu 2>/dev/null || nproc) cores / $(sysctl -n hw.memsize 2>/dev/null | awk '{printf "%.0fGB", $1/1073741824}' || free -h | awk '/Mem/ {print $2}')"

tune_system

# ── PHASE 1: Sync Server (single worker) ──
header "PHASE 1: SYNC SERVER (single worker)"
start_server "sync-1w" "bench.server_sync" 8100 1

run_endpoint_tiers "sync_1w" 8100 "/ping" "ping"
run_endpoint_tiers "sync_1w" 8100 "/items/42?fields=name" "path_query"
run_endpoint_tiers "sync_1w" 8100 "/heavy" "heavy_json"
run_endpoint_tiers "sync_1w" 8100 "/compute?n=100" "compute"
run_post_tiers "sync_1w" 8100
run_billion_test "sync_1w" 8100

stop_server

# ── PHASE 2: ASGI Server via uvicorn (single worker) ──
header "PHASE 2: ASGI SERVER via uvicorn (single worker)"
start_server "asgi-1w" "bench.server_asgi:asgi_app" 8101 1

run_endpoint_tiers "asgi_1w" 8101 "/ping" "ping"
run_endpoint_tiers "asgi_1w" 8101 "/items/42?fields=name" "path_query"
run_endpoint_tiers "asgi_1w" 8101 "/heavy" "heavy_json"
run_post_tiers "asgi_1w" 8101
run_billion_test "asgi_1w" 8101

stop_server

# ── PHASE 3: ASGI Server (4 workers) ──
header "PHASE 3: ASGI SERVER (4 workers)"
start_server "asgi-4w" "bench.server_asgi:asgi_app" 8101 4

run_endpoint_tiers "asgi_4w" 8101 "/ping" "ping"
run_endpoint_tiers "asgi_4w" 8101 "/heavy" "heavy_json"
run_billion_test "asgi_4w" 8101

stop_server

# ── PHASE 4: Middleware Heavy Server ──
header "PHASE 4: MIDDLEWARE HEAVY (7-layer stack)"
start_server "mw-heavy" "bench.server_middleware_heavy" 8102 1

run_endpoint_tiers "mw_heavy" 8102 "/ping" "ping_7mw"
run_endpoint_tiers "mw_heavy" 8102 "/heavy" "heavy_7mw"
run_billion_test "mw_heavy" 8102

stop_server

# ── FINAL SUMMARY ──
header "═══ FINAL RESULTS SUMMARY ═══"
{
    echo "Rivex Extreme Load Test Results"
    echo "Date: $(date)"
    echo "Machine: $(uname -m) / $(sysctl -n hw.ncpu 2>/dev/null || nproc) cores"
    echo ""
    echo "Server | Endpoint | Tier | RPS | Latency (avg) | Errors"
    echo "-------|----------|------|-----|---------------|-------"

    for result_file in "$RESULTS_DIR"/*/*/wrk_*.txt; do
        if [[ -f "$result_file" ]]; then
            local_path="${result_file#$RESULTS_DIR/}"
            server=$(echo "$local_path" | cut -d/ -f1)
            endpoint=$(echo "$local_path" | cut -d/ -f2)
            tier=$(basename "$result_file" .txt | sed 's/wrk_//')
            rps=$(grep "Requests/sec" "$result_file" | awk '{print $2}' || echo "N/A")
            latency=$(grep "Latency" "$result_file" | head -1 | awk '{print $2}' || echo "N/A")
            errors=$(grep -c "Non-2xx\|Socket errors" "$result_file" 2>/dev/null || echo "0")
            echo "$server | $endpoint | $tier | $rps | $latency | $errors"
        fi
    done
} | tee "$RESULTS_DIR/SUMMARY.txt"

echo ""
log "All results saved to: $RESULTS_DIR"
ok "Extreme load test suite complete."
