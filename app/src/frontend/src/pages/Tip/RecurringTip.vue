<script setup>
const props = defineProps({
  job: String
})

function formatTipAmount(amount) {
  return "$" + (amount / 100).toFixed(2)
}

function cancel() {
  fetch("/api/tip/cancel_recurring", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      recurring_tip_id: recurringTip.value.id
    })
  })
    .then(function (response) {
      if (response.status !== 200) {
        alert(
          "Error canceling recurring tip, please contact hi@semiphemeral.com: " +
          response.status
        )
        return
      }
      response.json().then(function (data) {
        if (that.error) {
          alert(error_message)
        } else {
          // Success, reload the tips page
          alert("Monthly tip canceled")
          window.location.href = "/tip"
        }
      })
    })
    .catch(function (err) {
      console.log("Error", err)
    })
}
</script>

<template>
  <div>
    <p>
      <span class="recurring-tip">You are currently tipping
        {{ formatTipAmount(recurringTip.amount) }} every month. Thank you!</span>
      <button v-on:click="cancel" type="button" id="cancel-recurring-tip" class="cancel-button">
        Cancel Recurring Tip
      </button>
    </p>
  </div>
</template>

<style scoped>
button {
  border: none;
  color: #5d8fad;
  text-decoration: underline;
  display: inline-block;
  cursor: pointer;
  font-weight: normal;
  font-size: 0.9em;
  background-color: #ffffff;
}

.recurring-tip {
  font-style: italic;
  font-size: 0.9em;
}
</style>