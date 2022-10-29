<script setup>
import { ref } from "vue"

const props = defineProps({
  userScreenName: String
})

const loading = ref(false)
const tips = ref([])

function fetchTips() {
  loading.value = true;

  // Get lists of tips
  fetch("/admin_api/tips")
    .then(function (response) {
      if (response.status !== 200) {
        console.log("Error fetching tips, status code: " + response.status)
        loading.value = false
        return
      }
      response.json().then(function (data) {
        loading.value = false
        if (data["tips"]) {
          tips.value = data["tips"]
        } else {
          tips.value = []
        }
      })
    })
    .catch(function (err) {
      console.log("Error fetching tips", err)
      loading.value = false
    })
}

function formatTipDate(timestamp) {
  var date = new Date(timestamp * 1000)
  var month_num = date.getMonth() + 1
  var month = ""
  if (month_num == 1) {
    month = "January"
  } else if (month_num == 2) {
    month = "February"
  } else if (month_num == 3) {
    month = "March"
  } else if (month_num == 4) {
    month = "April"
  } else if (month_num == 5) {
    month = "May"
  } else if (month_num == 6) {
    month = "June"
  } else if (month_num == 7) {
    month = "July"
  } else if (month_num == 8) {
    month = "August"
  } else if (month_num == 9) {
    month = "September"
  } else if (month_num == 10) {
    month = "October"
  } else if (month_num == 11) {
    month = "November"
  } else if (month_num == 12) {
    month = "December"
  }
  return month + " " + date.getDate() + ", " + date.getFullYear()
}

function formatTipAmount(amount) {
  return "$" + (amount / 100).toFixed(2)
}

fetchTips()
</script>

<template>
  <div>
    <h1>Tips</h1>

    <template v-if="loading">
      <p>
        <img src="/images/loading.gif" alt="Loading" />
      </p>
    </template>
    <template v-else>
      <div v-if="tips.length > 0">
        <h2>{{ tips.length }} tips</h2>
        <ul>
          <li v-for="(tip, index) in tips" v-bind:key="index">
            <span class="tip-user">
              <a v-bind:href="tip.twitter_link" target="_blank">{{
                  tip.twitter_username
              }}</a>
            </span>
            <span class="tip-date">{{ formatTipDate(tip.timestamp) }}</span>
            <span class="tip-amount">
              <template v-if="tip.refunded">
                <span class="refunded-amount">{{ formatTipAmount(tip.amount) }}</span>
                <span class="refunded">refunded</span>
              </template>
              <template v-else>{{ formatTipAmount(tip.amount) }}</template>
            </span>
            <span class="tip-receipt">
              <a v-bind:href="tip.receipt_url" target="_blank">
                <img title="Receipt" alt="Receipt" src="/images/receipt.png" />
              </a>
            </span>
          </li>
        </ul>
      </div>
    </template>
  </div>
</template>

<style scoped>
ul {
  list-style: none;
  padding: 0;
}

li img {
  width: 20px;
  height: 20px;
}

li .tip-user {
  display: inline-block;
  vertical-align: middle;
  margin-right: 0.5em;
  width: 150px;
  font-size: 0.9em;
}

li .tip-date {
  display: inline-block;
  vertical-align: middle;
  margin-right: 0.5em;
  width: 160px;
  font-size: 0.8em;
  color: #666666;
}

li .tip-amount {
  display: inline-block;
  vertical-align: middle;
  font-size: 0.8em;
  color: #009900;
  min-width: 80px;
  margin-right: 10px;
}

li .tip-amount .refunded-amount {
  text-decoration: line-through
}

li .tip-amount .refunded {
  color: #cc0000;
}

li .tip-receipt {
  display: inline-block;
  vertical-align: middle;
  width: 30px;
}
</style>