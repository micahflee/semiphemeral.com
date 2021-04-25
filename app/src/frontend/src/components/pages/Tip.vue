<style scoped>
fieldset {
  margin-bottom: 10px;
  max-width: 550px;
}

fieldset ul {
  list-style: none;
  padding: 0;
}

fieldset li {
  display: inline-block;
}

fieldset .other-amount {
  width: 2.5em;
}

fieldset label {
  background-color: #ffffff;
  color: #28404f;
  border: 1px solid #adc6d6;
  padding: 5px 10px;
  border-radius: 10px;
}

fieldset label.selected {
  background-color: #5d8fad;
  color: #ffffff;
  border: 1px solid #adc6d6;
  padding: 5px 10px;
  border-radius: 10px;
}

fieldset label input[type="radio"] {
  display: none;
}

button {
  background-color: #4caf50;
  border: none;
  color: white;
  padding: 5px 20px;
  text-align: center;
  text-decoration: none;
  display: inline-block;
  cursor: pointer;
  font-weight: bold;
  border-radius: 5px;
  margin: 0 0 5px 0;
}

.tips-history {
  margin-top: 30px;
}

.tips-history ul {
  list-style: none;
  padding: 0;
}

.tips-history li img {
  width: 20px;
  height: 20px;
}

.tips-history li .tip-date {
  display: inline-block;
  vertical-align: middle;
  margin-right: 0.5em;
  width: 120px;
  font-size: 0.8em;
  color: #666666;
}

.tips-history li .tip-amount {
  display: inline-block;
  vertical-align: middle;
  font-size: 0.8em;
  color: #009900;
  min-width: 55px;
  margin-right: 10px;
}

.tips-history li .tip-amount .refunded {
  color: #cc0000;
}

.tips-history li .tip-receipt {
  display: inline-block;
  vertical-align: middle;
  width: 30px;
}
</style>

<template>
  <div>
    <h1>Care to chip in?</h1>
    <p>
      Semiphemeral is free. Every day a bot will automatically delete your old
      tweets and likes (except for the ones you want to keep), keeping your
      social media presence a bit more private.
      <strong
        >Hosting this service costs money though, so tips are
        appreciated.</strong
      >
    </p>

    <template v-if="recurringTips.length > 0" class="recurring-tips">
      <li v-for="(recurringTip, index) in recurringTips" v-bind:key="index">
        <RecurringTip v-bind:recurringTip="recurringTip"></RecurringTip>
      </li>
    </template>

    <fieldset>
      <legend>How much would you like to tip?</legend>
      <ul>
        <li>
          <label v-bind:class="amount == '100' ? 'selected' : ''">
            <input type="radio" name="amount" value="100" v-model="amount" />
            $1
          </label>
        </li>
        <li>
          <label v-bind:class="amount == '500' ? 'selected' : ''">
            <input type="radio" name="amount" value="500" v-model="amount" />
            $5
          </label>
        </li>
        <li>
          <label v-bind:class="amount == '1337' ? 'selected' : ''">
            <input type="radio" name="amount" value="1337" v-model="amount" />
            $13.37
          </label>
        </li>
        <li>
          <label v-bind:class="amount == '2000' ? 'selected' : ''">
            <input type="radio" name="amount" value="2000" v-model="amount" />
            $20
          </label>
        </li>
        <li>
          <label v-bind:class="amount == '10000' ? 'selected' : ''">
            <input type="radio" name="amount" value="10000" v-model="amount" />
            $100
          </label>
        </li>
        <li>
          <label v-bind:class="amount == 'other' ? 'selected' : ''">
            <input type="radio" name="amount" value="other" v-model="amount" />
            Other
          </label>
          <span v-if="amount == 'other'">
            $
            <input
              type="text"
              v-model.number="otherAmount"
              class="other-amount"
            />
          </span>
        </li>
      </ul>
      <ul>
        <li>
          <label v-bind:class="type == 'one-time' ? 'selected' : ''">
            <input type="radio" name="type" value="one-time" v-model="type" />
            One-time
          </label>
        </li>
        <li>
          <label v-bind:class="type == 'monthly' ? 'selected' : ''">
            <input type="radio" name="type" value="monthly" v-model="type" />
            Monthly
          </label>
        </li>
      </ul>
    </fieldset>

    <p>
      <button v-bind:disabled="loading" type="button" id="tip-stripe-button">
        Tip with Credit Card
      </button>
      <img v-if="loading" src="/static/img/loading.gif" alt="Loading" />
    </p>

    <div v-if="tips.length > 0" class="tips-history">
      <p>
        <strong>Your history of tips</strong>
      </p>
      <ul>
        <li v-for="(tip, index) in tips" v-bind:key="index">
          <span class="tip-date">{{ formatTipDate(tip.timestamp) }}</span>
          <span class="tip-amount">
            <template v-if="tip.refunded">
              <strike>{{ formatTipAmount(tip.amount) }}</strike>
              <span class="refunded">refunded</span>
            </template>
            <template v-else>{{ formatTipAmount(tip.amount) }}</template>
          </span>
          <span class="tip-receipt">
            <a v-bind:href="tip.receipt_url" target="_blank">
              <img
                title="Receipt"
                alt="Receipt"
                src="/static/img/receipt.png"
              />
            </a>
          </span>
        </li>
      </ul>
    </div>
  </div>
</template>

<script>
import RecurringTip from "./Tip/RecurringTip.vue";

export default {
  props: ["userScreenName"],
  data: function () {
    return {
      loading: false,
      errorMessage: null,
      stripePublishableKey: false,
      stripe: false,
      amount: "500",
      otherAmount: "",
      type: "one-time",
      tips: [],
      recurringTips: [],
    };
  },
  created: function () {
    var that = this;
    fetch("/api/tip")
      .then(function (response) {
        if (response.status !== 200) {
          console.log(
            "Error fetching tip info, status code: " + response.status
          );
          return;
        }
        response.json().then(function (data) {
          that.stripePublishableKey = data["stripe_publishable_key"];
          that.tips = data["tips"];
          that.recurringTips = data["recurring_tips"];

          that.initStripe();
        });
      })
      .catch(function (err) {
        console.log("Error fetching tip info", err);
      });
  },
  methods: {
    initStripe: function () {
      // Initialize Stripe
      this.stripe = Stripe(this.stripePublishableKey);
      var tipButton = document.getElementById("tip-stripe-button");

      var that = this;
      tipButton.addEventListener("click", function () {
        fetch("/api/tip", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            amount: that.amount,
            other_amount: that.otherAmount,
            type: that.type,
          }),
        })
          .then(function (response) {
            return response.json();
          })
          .then(function (session) {
            return that.stripe.redirectToCheckout({ sessionId: session.id });
          })
          .then(function (result) {
            if (result.error) {
              alert(result.error.message);
            }
          })
          .catch(function (error) {
            console.error("Error:", error);
          });
      });
    },
    formatTipDate: function (timestamp) {
      var date = new Date(timestamp * 1000);
      var month_num = date.getMonth() + 1;
      var month = "";
      if (month_num == 1) {
        month = "January";
      } else if (month_num == 2) {
        month = "February";
      } else if (month_num == 3) {
        month = "March";
      } else if (month_num == 4) {
        month = "April";
      } else if (month_num == 5) {
        month = "May";
      } else if (month_num == 6) {
        month = "June";
      } else if (month_num == 7) {
        month = "July";
      } else if (month_num == 8) {
        month = "August";
      } else if (month_num == 9) {
        month = "September";
      } else if (month_num == 10) {
        month = "October";
      } else if (month_num == 11) {
        month = "November";
      } else if (month_num == 12) {
        month = "December";
      }
      return month + " " + date.getDate() + ", " + date.getFullYear();
    },
    formatTipAmount: function (amount) {
      return "$" + (amount / 100).toFixed(2);
    },
  },
  components: {
    RecurringTip: RecurringTip,
  },
};
</script>