Vue.component('tip', {
    data: function () {
        return {
            loading: false,
            stripePublishableKey: false,
            stripe: false,
            stripeCard: false,
            amount: "500",
            otherAmount: ""
        }
    },
    created: function () {
        var that = this;
        fetch("/api/tip")
            .then(function (response) {
                if (response.status !== 200) {
                    console.log('Error fetching tip variables, status code: ' + response.status);
                    return;
                }
                response.json().then(function (data) {
                    that.stripePublishableKey = data['stripe_publishable_key'];
                    that.initStripe()
                })
            })
            .catch(function (err) {
                console.log("Error fetching tip variables", err)
            })
    },
    methods: {
        initStripe: function () {
            // Initialize Stripe
            this.stripe = Stripe(this.stripePublishableKey);
            var elements = this.stripe.elements();

            // Create a card element, attach it to the div
            this.stripeCard = elements.create('card');
            this.stripeCard.mount('#card-element');
        },
        onSubmit: function () {
            that = this;
            this.loading = true;

            this.stripe.createToken(this.stripeCard).then(function (result) {
                if (result.error) {
                    // Inform the customer that there was an error
                    var errorElement = document.getElementById('card-errors');
                    errorElement.textContent = result.error.message;
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
                        .then(function (response) {
                            that.loading = false;
                            response.json().then(function (data) {
                                if (data['error']) {
                                    var errorElement = document.getElementById('card-errors');
                                    errorElement.textContent = data['error_message'];
                                } else {
                                    // No error, reload tips history
                                }

                                that.loading = false;
                            })
                        })
                        .catch(function (err) {
                            console.log("Error submitting card", err)
                            var errorElement = document.getElementById('card-errors');
                            errorElement.textContent = "Error submitting card: " + err;

                            that.loading = false;
                        })
                }
            });
        }
    },
    template: `
        <div class="page tip">
            <h1>Care to chip in?</h1>
            <p>Semiphemeral is free. Every day a bot will automatically delete your old tweets and likes except for the ones you want to keep, keeping your social media presence a bit more private. Hosting this service costs money though, so tips are appreciated.</p>

            <p>As long as you're using this service, the @semiphemeral Twitter account will gently ask you for a tip, via Twitter DM, once a month. If you donate any amount, even just $1, it will stop nagging you for a year.</p>

            <form action="/api/tip" method="post" v-on:submit.prevent="onSubmit">
                <fieldset>
                    <legend>How much would you like to tip?</legend>
                    <ul>
                        <li><label><input type="radio" name="amount" value="100" v-model="amount" /> $1</label></li>
                        <li><label><input type="radio" name="amount" value="200" v-model="amount" /> $2</label></li>
                        <li><label><input type="radio" name="amount" value="500" v-model="amount" /> $5</label></li>
                        <li><label><input type="radio" name="amount" value="1000" v-model="amount" /> $10</label></li>
                        <li><label><input type="radio" name="amount" value="5000" v-model="amount" /> $50</label></li>
                        <li>
                            <label><input type="radio" name="amount" value="other" v-model="amount" /> Other</label>
                            <span v-if="amount == 'other'">$<input type="text" v-model.number="otherAmount" class="other-amount" /></span>
                        </li>
                    </ul>
                </fieldset>
                <fieldset>
                    <legend>Credit or debit card</legend>
                    <div id="card-element"></div>
                </fieldset>

                <div id="card-errors" role="alert"></div>

                <p>
                    <input v-bind:disabled="loading" type="submit" value="Tip" />
                    <img v-if="loading" src="/static/img/loading.gif" alt="Loading" />
                </p>
            </form>
        </div>
    `
})