import tweepy
from google.cloud import bigquery, functions
from google.cloud.bigquery import QueryJobConfig, ScalarQueryParameter
from datetime import datetime, timedelta
from llm import get_model_response
import schedule
import time
import os
import logging
from dotenv import load_dotenv
import functions_framework

load_dotenv()

logging.basicConfig(level=logging.INFO)


X_API_KEY = os.getenv("X_API_KEY")
X_API_KEY_SECRET = os.getenv("X_API_KEY_SECRET")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN")
X_ACCESS_TOKEN_SECRET = os.getenv("X_ACCESS_TOKEN_SECRET")
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN")

BIGQUERY_PROJECT_ID = os.getenv("BIGQUERY_PROJECT_ID")
BIGQUERY_DATASET_ID = os.getenv("BIGQUERY_DATASET_ID")
BIGQUERY_TABLE_ID = os.getenv("BIGQUERY_TABLE_ID")


class AiyshaBot:
    def __init__(self):        
        self.twitter_api = tweepy.Client(bearer_token=X_BEARER_TOKEN,
                                         consumer_key=X_API_KEY,
                                         consumer_secret=X_API_KEY_SECRET,
                                         access_token=X_ACCESS_TOKEN,
                                         access_token_secret=X_ACCESS_TOKEN_SECRET,
                                         wait_on_rate_limit=True)

        self.bigquery_client = bigquery.Client(project=BIGQUERY_PROJECT_ID)
        self.bigquery_table_ref = self.bigquery_client.dataset(BIGQUERY_DATASET_ID).table(BIGQUERY_TABLE_ID)
        self.twitter_me_id = self.get_me_id()
        self.tweet_response_limit = 25  

        self.mentions_found = 0
        self.mentions_replied = 0
        self.mentions_replied_errors = 0
        
        self.retry_delay = 60 
        self.max_retries = 5
    
    def get_me_id(self):
        me = self.twitter_api.get_me()
        return me.data.id
    
    # def get_mention_conversation_tweet(self, mention):
    #     conversation_id = mention.conversation_id
    #     conversation_tweets = self.twitter_api.get_users_mentions(id=self.twitter_me_id, tweet_fields=['created_at', 'conversation_id'])
    #     for tweet in conversation_tweets.data:
    #         if tweet.id != mention.id:
    #             return tweet
    #     return None
        
    def get_mention_tweet(self, mention):
        tweet_id = mention.conversation_id
        original_tweet = self.twitter_api.get_tweet(id=tweet_id, tweet_fields=['text'])
        if original_tweet.data:
            return original_tweet.data
        else:
            return None
    
    def get_mentions(self):
        now = datetime.utcnow()
        start_time = now - timedelta(minutes=20)
        start_time_str = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        mentions = []
        max_results = 100
        next_token = None
        while True:
            try:
                response = self.twitter_api.get_users_mentions(id=self.twitter_me_id,
                                                            start_time=start_time_str,
                                                            expansions=['referenced_tweets.id'],
                                                            tweet_fields=['created_at', 'conversation_id'],
                                                            max_results=max_results,
                                                            pagination_token=next_token)
            except tweepy.RateLimitError as e:
                logging.warning(f"Rate limit exceeded: {e}")
                self.retry_get_mentions()
            if response.data:
                mentions.extend(response.data)
            next_token = response.meta.get('next_token')
            if not next_token:
                break
            
        return mentions
    
    def retry_get_mentions(self):
        retries = 0
        while retries < self.max_retries:
            try:
                response = self.twitter_api.get_users_mentions(id=self.twitter_me_id,
                                                            start_time=start_time_str,
                                                            expansions=['referenced_tweets.id'],
                                                            tweet_fields=['created_at', 'conversation_id'],
                                                            max_results=max_results,
                                                            pagination_token=next_token)
                break
            except tweepy.RateLimitError as e:
                logging.warning(f"Rate limit exceeded (retry {retries+1}): {e}")
                time.sleep(self.retry_delay)
                retries += 1
        if retries == self.max_retries:
            logging.error("Max retries reached. Skipping.")
            return []
        return response
    
    def respond_to_mention(self, mention, mentioned_conversation_tweet):
        response_text = get_model_response(mentioned_conversation_tweet.text)
        if len(response_text) > 280:
            response_text = response_text[:280]
        
        try:
            response_tweet = self.twitter_api.create_tweet(text=response_text, in_reply_to_tweet_id=mention.id)
            self.mentions_replied += 1
        except tweepy.RateLimitError as e:
            logging.warning(f"Rate limit exceeded: {e}")
            self.mentions_replied_errors += 1
            self.retry_create_tweet(mention, mentioned_conversation_tweet)
        
        table = self.bigquery_client.get_table(self.bigquery_table_ref)
        table_schema = table.schema
        
        row_to_insert = [
            {u'mentioned_conversation_tweet_id': str(mention.id),
             u'mentioned_conversation_tweet_text': mentioned_conversation_tweet.text,
             u'tweet_response_id': str(response_tweet.data['id']),
             u'tweet_response_text': response_text,
             u'tweet_response_created_at': datetime.utcnow().isoformat(),
             u'mentioned_at': mention.created_at.isoformat()
            }
        ]
        self.bigquery_client.insert_rows(self.bigquery_table_ref, row_to_insert, table_schema)
        
        logging.info("Table successfully updated")
        
    def retry_create_tweet(self, mention, mentioned_conversation_tweet):
        retries = 0
        while retries < self.max_retries:
            try:
                response_tweet = self.twitter_api.create_tweet(text=response_text, in_reply_to_tweet_id=mention.id)
                self.mentions_replied += 1
                break
            except tweepy.RateLimitError as e:
                logging.warning(f"Rate limit exceeded (retry {retries+1}): {e}")
                time.sleep(self.retry_delay)
                retries += 1
        if retries == self.max_retries:
            logging.error("Max retries reached. Skipping.")
            return
    
    def check_already_responded(self, mention):
        query = f"""
            SELECT COUNT(*) as count
            FROM `{BIGQUERY_PROJECT_ID}.{BIGQUERY_DATASET_ID}.{BIGQUERY_TABLE_ID}`
            WHERE mentioned_conversation_tweet_id = CAST(@tweet_id AS STRING)
        """
        query_params = [ScalarQueryParameter('tweet_id', 'INTEGER', mention.id)]
        job_config = QueryJobConfig(query_parameters=query_params)
        query_job = self.bigquery_client.query(query, job_config=job_config)
        result = query_job.result()
        count = list(result)[0].count
        return count > 0
    
    def respond_to_mentions(self):
        mentions = self.get_mentions()
        self.mentions_found = len(mentions)
        
        for mention in mentions:
            mentioned_conversation_tweet = self.get_mention_tweet(mention)
            if mentioned_conversation_tweet and not self.check_already_responded(mention):
                self.respond_to_mention(mention, mentioned_conversation_tweet)

    def execute_replies(self):
        logging.info(f"Starting Job: {datetime.utcnow().isoformat()}")
        try:
            self.respond_to_mentions()
        except Exception as e:
            logging.info(e)
        logging.info(f"Finished Job: {datetime.utcnow().isoformat()}, Found: {self.mentions_found}, Replied: {self.mentions_replied}, Errors: {self.mentions_replied_errors}")
        
    # def tweet(self):
    #     response_text = get_model_response("what is a funny and interesting beauty fact?")
    #     self.twitter_api.create_tweet(text=response_text)
    #     logging.info("Tweeted successfully")
    
@functions_framework.http
def aiysha_bot(request):
    logging.info(f"Job executed at {datetime.utcnow().isoformat()}")
    bot = AiyshaBot()
    bot.execute_replies()
    logging.info("Aiysha executed successfully!")
    return "Aiysha X bot executed successfully!"
    

# def job():
#     logging.info(f"Job executed at {datetime.utcnow().isoformat()}")
#     bot = AiyshaBot()
#     bot.execute_replies()
#     # bot.tweet()
    

# if __name__ == "__main__":
#     schedule.every(5).minutes.do(job)
#     while True:
#         if schedule.run_pending():
#             logging.info("Task executed successfully")
#         else:
#             logging.info("No tasks pending")
#         time.sleep(1)