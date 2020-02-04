<style scoped>
form fieldset {
  margin-bottom: 10px;
  max-width: 450px;
}

form ul {
  list-style: none;
  padding: 0;
}

form li {
  display: inline-block;
}

form .other-amount {
  width: 2.5em;
}

form #card-element {
  max-width: 440px;
  border: 1px solid #f0f0f0;
  padding: 5px;
}

form #card-errors {
  color: #cc0000;
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
    <script src="https://js.stripe.com/v3/"></script>
    <h1>Care to chip in?</h1>
    <p>Semiphemeral is free. Every day a bot will automatically delete your old tweets and likes except for the ones you want to keep, keeping your social media presence a bit more private. Hosting this service costs money though, so tips are appreciated.</p>

    <p>As long as you're using this service, the @semiphemeral Twitter account will gently ask you for a tip, via Twitter DM, once a month. If you tip any amount, even just $1, it will stop nagging you for a year.</p>

    <form action="/api/tip" method="post" v-on:submit.prevent="onSubmit">
      <fieldset>
        <legend>How much would you like to tip?</legend>
        <ul>
          <li>
            <label>
              <input type="radio" name="amount" value="100" v-model="amount" /> $1
            </label>
          </li>
          <li>
            <label>
              <input type="radio" name="amount" value="500" v-model="amount" /> $5
            </label>
          </li>
          <li>
            <label>
              <input type="radio" name="amount" value="1337" v-model="amount" /> $13.37
            </label>
          </li>
          <li>
            <label>
              <input type="radio" name="amount" value="2000" v-model="amount" /> $20
            </label>
          </li>
          <li>
            <label>
              <input type="radio" name="amount" value="other" v-model="amount" /> Other
            </label>
            <span v-if="amount == 'other'">
              $
              <input type="text" v-model.number="otherAmount" class="other-amount" />
            </span>
          </li>
        </ul>
      </fieldset>
      <fieldset>
        <legend>Credit or debit card</legend>
        <div id="card-element"></div>
      </fieldset>

      <div v-if="errorMessage" id="card-errors">{{ errorMessage }}</div>

      <p>
        <input v-bind:disabled="loading" type="submit" value="Tip" />
        <img v-if="loading" src="/static/img/loading.gif" alt="Loading" />
      </p>
    </form>
    <div v-if="tips.length > 0" class="tips-history">
      <p>
        <strong>Your history of tips</strong>
      </p>
      <ul>
        <li v-for="tip in tips">
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
              <img title="Receipt" alt="Receipt" src="/static/img/receipt.png" />
            </a>
          </span>
        </li>
      </ul>
    </div>
  </div>
</template>

<script>
export default {
  props: ["userScreenName"],
  data: function() {
    return {
      loading: false,
      errorMessage: null,
      stripePublishableKey: false,
      stripe: false,
      stripeCard: false,
      amount: "500",
      otherAmount: "",
      tips: []
    };
  },
  created: function() {
    var that = this;

    // Get the publishable Stripe API key
    fetch("/api/tip")
      .then(function(response) {
        if (response.status !== 200) {
          console.log(
            "Error fetching tip variables, status code: " + response.status
          );
          return;
        }
        response.json().then(function(data) {
          that.stripePublishableKey = data["stripe_publishable_key"];
          that.initStripe();
        });
      })
      .catch(function(err) {
        console.log("Error fetching tip variables", err);
      });

    this.fetchHistory();
  },
  methods: {
    fetchHistory: function() {
      var that = this;

      // Get the history of tips
      fetch("/api/tip/history")
        .then(function(response) {
          if (response.status !== 200) {
            console.log(
              "Error fetching tip history, status code: " + response.status
            );
            return;
          }
          response.json().then(function(data) {
            that.tips = data;
          });
        })
        .catch(function(err) {
          console.log("Error fetching tip history", err);
        });
    },
    initStripe: function() {
      // Initialize Stripe
      this.stripe = Stripe(this.stripePublishableKey);
      var elements = this.stripe.elements();

      // Create a card element, attach it to the div
      this.stripeCard = elements.create("card");
      this.stripeCard.mount("#card-element");
    },
    onSubmit: function() {
      var that = this;
      this.errorMessage = null;
      this.loading = true;

      this.stripe.createToken(this.stripeCard).then(function(result) {
        if (result.error) {
          that.errorMessage = result.error.message;
          that.loading = false;
        } else {
          // Send the token to the server
          var token = result.token;

          fetch("/api/tip", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              token: token.id,
              amount: that.amount,
              other_amount: that.otherAmount
            })
          })
            .then(function(response) {
              that.loading = false;
              response.json().then(function(data) {
                if (data["error"]) {
                  that.errorMessage = data["error_message"];
                } else {
                  that.fetchHistory();

                  // Navigate to thank you page
                  that.$router.push("/thanks");
                }

                that.loading = false;
              });
            })
            .catch(function(err) {
              console.log("Error submitting card", err);
              that.errorMessage = "Error submitting card: " + err;
              that.loading = false;
            });
        }
      });
    },
    formatTipDate: function(timestamp) {
      var date = new Date(timestamp * 1000);
      var month_num = date.getMonth() + 1;
      var month = "";
      if (month_num == 1) {
        month = "January";
      } else if (month_num == 2) {
        month = "February";
      } else if (month_num == 2) {
        month = "March";
      } else if (month_num == 2) {
        month = "April";
      } else if (month_num == 2) {
        month = "May";
      } else if (month_num == 2) {
        month = "June";
      } else if (month_num == 2) {
        month = "July";
      } else if (month_num == 2) {
        month = "August";
      } else if (month_num == 2) {
        month = "September";
      } else if (month_num == 2) {
        month = "October";
      } else if (month_num == 2) {
        month = "November";
      } else if (month_num == 2) {
        month = "December";
      }
      return month + " " + date.getDate() + ", " + date.getFullYear();
    },
    formatTipAmount: function(amount) {
      return "$" + (amount / 100).toFixed(2);
    }
  }
};
</script>