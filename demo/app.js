/* TerraCycle Proof — read-only demonstration page.
 *
 * Loads the verified demonstration snapshot from the local server and renders
 * it. There is no hardcoded data here: every value comes from the JSON.
 * The page never triggers a blockchain transaction and never contacts an
 * external service.
 */
(function () {
  "use strict";

  var PROOF_URL = "/api/proof";

  function $(id) {
    return document.getElementById(id);
  }

  function setText(id, value) {
    var node = $(id);
    if (!node) return;
    if (value === null || value === undefined || value === "") {
      node.textContent = "–";
      return;
    }
    node.textContent = String(value);
  }

  function showError(message) {
    var panel = $("error-panel");
    var content = $("content");
    if (content) content.hidden = true;
    if (panel) {
      setText("error-message", message);
      panel.hidden = false;
    }
    var meta = $("run-meta");
    if (meta) meta.textContent = "The demonstration snapshot could not be loaded.";
  }

  function formatTimestamp(value) {
    if (!value) return null;
    var parsed = new Date(value);
    if (isNaN(parsed.getTime())) return String(value);
    return parsed.toISOString().replace("T", " ").replace(/\.\d+Z$/, " UTC");
  }

  function formatPercent(value) {
    if (value === null || value === undefined) return null;
    return (Number(value) * 100).toFixed(0) + "%";
  }

  function verdictClass(verdict) {
    var v = String(verdict || "").toLowerCase();
    if (v === "conform") return "verdict-conform";
    if (v === "nonconform") return "verdict-nonconform";
    if (v === "inconclusive") return "verdict-inconclusive";
    return "verdict-unknown";
  }

  function renderParcel(data) {
    var parcel = data.parcel || {};
    setText("p-parcel-id", parcel.parcel_id);
    setText("p-season-id", parcel.season_id);
    setText("p-provider", parcel.satellite_provider);
    setText("p-dataset", parcel.satellite_dataset);
    setText("p-method", parcel.satellite_method);
    setText("p-source-csv", parcel.source_csv);
    if (parcel.observations_total !== undefined && parcel.observations_total !== null) {
      setText(
        "p-observations",
        parcel.observations_total +
          " observations (" +
          parcel.observations_valid +
          " valid)"
      );
    }
    setText("p-rows", parcel.source_rows);
  }

  function renderVerification(data) {
    var verification = data.verification || {};
    var verdictNode = $("v-verdict");
    if (verdictNode) {
      verdictNode.textContent = verification.verdict || "unknown";
      verdictNode.className = "verdict " + verdictClass(verification.verdict);
    }
    setText("v-verdict-code", "verdict code " + (verification.verdict_code !== undefined ? verification.verdict_code : "–"));
    setText("v-reason", verification.reason);
    setText("v-reason-code", verification.reason_code);

    var policy = verification.policy_version
      ? verification.policy_version +
        (verification.policy_type ? " (" + verification.policy_type + ")" : "")
      : null;
    setText("v-policy", policy);

    var windowText = null;
    if (verification.window_start || verification.window_end) {
      windowText = (verification.window_start || "–") + " → " + (verification.window_end || "–");
    }
    setText("v-window", windowText);
    setText("v-threshold", verification.ndvi_threshold);
    setText("v-fraction", verification.required_fraction);
    setText("v-quality", verification.evidence_quality);
    setText("v-coverage", formatPercent(verification.temporal_coverage));

    var warnings = verification.evidence_quality_warnings || [];
    var list = $("v-warnings");
    if (list) {
      list.innerHTML = "";
      warnings.forEach(function (warning) {
        var item = document.createElement("li");
        item.textContent = warning;
        list.appendChild(item);
      });
    }
  }

  function renderEvidence(data) {
    var evidence = data.evidence || {};
    setText("e-commitment-id", evidence.commitment_id);
    setText("e-evidence-id", evidence.evidence_id);
    setText("e-evidence-hash", evidence.evidence_hash);
    setText("e-evidence-hash-recomputed", evidence.evidence_hash_recomputed);
    setText("e-bytes", evidence.canonical_bytes_length ? evidence.canonical_bytes_length + " canonical bytes" : null);
    setText("e-schema", evidence.schema_version);
    setText("e-plan-id", evidence.plan_id);
    setText("e-plan-hash", evidence.plan_hash);
  }

  function renderBlockchain(data) {
    var chain = data.blockchain || {};
    var onChain = chain.on_chain || {};
    var event = chain.event || {};

    setText("c-network", chain.network);
    setText("c-chain-id", chain.chain_id);
    setText("c-registry", chain.registry_address);
    setText("c-tx-hash", chain.tx_hash);
    setText("c-deploy-tx", chain.deploy_tx_hash);
    setText("c-status", chain.receipt_status === 1 ? "1 — successful" : chain.receipt_status);
    setText(
      "c-event",
      event.name
        ? event.name + " (commitment " + (event.commitment_id || "–") + ")"
        : null
    );
    setText("c-recorder", event.recorder);
    setText(
      "c-readback",
      onChain.read_back_match === true
        ? "MATCH — the contract stores the same commitment id, evidence hash and verdict"
        : onChain.read_back_match === false
          ? "MISMATCH"
          : null
    );
  }

  function renderIntegrity(data) {
    var integrity = data.integrity || {};
    var list = $("integrity");
    if (!list) return;
    list.innerHTML = "";
    Object.keys(integrity).forEach(function (name) {
      var item = document.createElement("li");
      item.textContent = name.replace(/_/g, " ") + ": " + (integrity[name] ? "verified" : "FAILED");
      list.appendChild(item);
    });
  }

  function renderLimitations(data) {
    var limitations = data.limitations || [];
    var list = $("limitations");
    if (!list) return;
    list.innerHTML = "";
    limitations.forEach(function (text) {
      var item = document.createElement("li");
      item.textContent = text;
      list.appendChild(item);
    });
  }

  function renderMeta(data) {
    var run = data.run || {};
    var parts = [];
    var generated = formatTimestamp(data.generated_at);
    if (generated) parts.push("snapshot generated " + generated);
    if (run.network) parts.push("network " + run.network);
    if (run.chain_id) parts.push("chain id " + run.chain_id);
    if (run.local_only) parts.push("local chain only — not a public testnet");
    var meta = $("run-meta");
    if (meta) meta.textContent = parts.join(" · ");
  }

  function wireCopyButtons() {
    var buttons = document.querySelectorAll(".copy");
    Array.prototype.forEach.call(buttons, function (button) {
      button.addEventListener("click", function () {
        var target = $(button.getAttribute("data-copy-target"));
        if (!target) return;
        var value = target.textContent || "";
        var done = function () {
          var original = button.textContent;
          button.textContent = "Copied";
          window.setTimeout(function () {
            button.textContent = original;
          }, 1500);
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(value).then(done, function () {});
        }
      });
    });
  }

  function render(data) {
    renderMeta(data);
    renderParcel(data);
    renderVerification(data);
    renderEvidence(data);
    renderBlockchain(data);
    renderIntegrity(data);
    renderLimitations(data);
    wireCopyButtons();
    var content = $("content");
    var panel = $("error-panel");
    if (content) content.hidden = false;
    if (panel) panel.hidden = true;
  }

  function start() {
    fetch(PROOF_URL, { cache: "no-store" })
      .then(function (response) {
        return response.json().then(function (body) {
          if (!response.ok) {
            var message =
              (body && body.error && body.error.message) ||
              "The server returned HTTP " + response.status + ".";
            throw new Error(message);
          }
          return body;
        });
      })
      .then(function (data) {
        if (!data || typeof data !== "object" || !data.verification) {
          throw new Error("The demonstration document is malformed: expected sections are missing.");
        }
        render(data);
      })
      .catch(function (error) {
        showError(error && error.message ? error.message : "Unknown error while loading the demonstration data.");
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
