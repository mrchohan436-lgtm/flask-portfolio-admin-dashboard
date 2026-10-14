console.log("Abubakar's Flask portfolio loaded successfully 🚀");
// =========================
// ADVANCED MESSAGE INSIGHTS
// =========================

async function loadAdvancedMessageInsights() {

    try {

        // =========================
        // BASIC INSIGHTS
        // =========================

        const insightsResponse = await fetch(
            "/admin/dashboard/advanced-insights"
        );

        const insightsData = await insightsResponse.json();

        document.getElementById(
            "insight-total-messages"
        ).textContent = insightsData.total_messages;

        document.getElementById(
            "insight-unique-senders"
        ).textContent = insightsData.unique_senders;

        document.getElementById(
            "insight-repeat-senders"
        ).textContent = insightsData.repeat_senders;

        document.getElementById(
            "insight-response-rate"
        ).textContent =
            insightsData.response_rate + "%";

        document.getElementById(
            "insight-average-length"
        ).textContent =
            insightsData.average_message_length + " chars";


        // =========================
        // PEAK ACTIVITY
        // =========================

        const peakResponse = await fetch(
            "/admin/dashboard/peak-activity"
        );

        const peakData = await peakResponse.json();

        document.getElementById(
            "insight-busiest-day"
        ).textContent =
            peakData.busiest_day || "No data";

        document.getElementById(
            "insight-peak-hour"
        ).textContent =
            formatInsightHour(peakData.peak_hour);


        // =========================
        // MESSAGE BEHAVIOR
        // =========================

        const behaviorResponse = await fetch(
            "/admin/dashboard/message-behavior"
        );

        const behaviorData =
            await behaviorResponse.json();

        document.getElementById(
            "insight-short-messages"
        ).textContent =
            behaviorData.short_messages;

        document.getElementById(
            "insight-medium-messages"
        ).textContent =
            behaviorData.medium_messages;

        document.getElementById(
            "insight-long-messages"
        ).textContent =
            behaviorData.long_messages;

        document.getElementById(
            "insight-long-messages-2"
        ).textContent =
            behaviorData.long_messages;


        // =========================
        // SMART INSIGHTS
        // =========================

        const smartResponse = await fetch(
            "/admin/dashboard/smart-insights"
        );

        const smartData =
            await smartResponse.json();

        const insightsContainer =
            document.getElementById(
                "smart-insights-list"
            );

        insightsContainer.innerHTML = "";

        if (
            smartData.insights &&
            smartData.insights.length > 0
        ) {

            smartData.insights.forEach(function(insight) {

                const item =
                    document.createElement("p");

                item.textContent =
                    "• " + insight;

                insightsContainer.appendChild(item);

            });

        } else {

            insightsContainer.innerHTML =
                "<p>No insights available.</p>";

        }

    } catch (error) {

        console.error(
            "Advanced insights error:",
            error
        );

    }

}


// =========================
// FORMAT HOUR
// =========================

function formatInsightHour(hour) {

    if (hour === null || hour === undefined) {
        return "No data";
    }

    let numericHour = parseInt(hour);

    if (isNaN(numericHour)) {
        return "No data";
    }

    if (numericHour === 0) {
        return "12 AM";
    }

    if (numericHour < 12) {
        return numericHour + " AM";
    }

    if (numericHour === 12) {
        return "12 PM";
    }

    return (numericHour - 12) + " PM";
}


// =========================
// LOAD ON DASHBOARD
// =========================

document.addEventListener(
    "DOMContentLoaded",
    function() {

        if (
            document.getElementById(
                "insight-total-messages"
            )
        ) {

            loadAdvancedMessageInsights();

        }

    }
);