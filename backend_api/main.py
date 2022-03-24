from datetime import datetime
import logging
from flask import Flask
from flask_restx import Resource, Api
from google.cloud import datastore
from google.cloud import language_v1 as language
from google.cloud import language_v1
import os

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "key.json"

"""
This Flask app shows some examples of the types of requests you could build.
There is currently a GET request that will return all the data in GCP Datastore.
There is also a POST request that will analyse some given text then store the text and its sentiment in GCP Datastore.


The sentiment analysis of the text is being done by Google's NLP API. 
This API can be used to find the Sentiment, Entities, Entity-Sentiment, Syntax, and Content-classification of texts.
Find more about this API here:
https://cloud.google.com/natural-language/docs/basics
For sample code for implementation, look here (click 'Python' above the code samples):
https://cloud.google.com/natural-language/docs/how-to
Note: The analyze_text_sentiment() method below simply copies the 'Sentiment' part of the above documentation.


The database we are using is GCP Datastore (AKA Firestore in Datastore mode). 
This is a simple NoSQL Document database offering by Google:
https://cloud.google.com/datastore
You can access the database through the GCP Cloud Console (find Datastore in the side-menu)


Some ideas of things to build:
- At the moment, the code only stores the analysis of the first sentence of a given text. Modify the POST request to
 also analyse the rest of the sentences. 
- GET Request that returns a single entity based on its ID
- POST Request that will take a list of text items and give it a sentiment then store it in GCP Datastore
- DELETE Request to delete an entity from Datastore based on its ID
- Implement the other analyses that are possible with Google's NLP API


We are using Flask: https://flask.palletsprojects.com/en/2.0.x/
Flask RESTX is an extension of Flask that allows us to document the API with Swagger: https://flask-restx.readthedocs.io/en/latest/
"""

app = Flask(__name__)
api = Api(app)

parser = api.parser()
parser.add_argument("text", type=str, help="Text", location="form")


@api.route("/api/analyze")
class Analyze(Resource):
    @api.expect(parser)
    def post(self):
        datastore_client = datastore.Client()

        args = parser.parse_args()
        text = args["text"]

        #get overall sentiment
        sentiment = 0.0
        count = 0.0
        result = analyze_text_sentiment(text)
        for item in result:
            count = count + 1
            sentiment = sentiment + item.get("sentiment score")

        if(count>0):
            sentiment = sentiment / count

        # Assign a label based on the score
        overall_sentiment = getSentiment(sentiment)
        current_datetime = datetime.now()

        #load esg
        filterEsgWords = open('ESG_Keywords.txt', "r").readlines()
        words = [w.lower().strip() for w in filterEsgWords]

        #get the entities
        entities=analyze_entity_sentiment(text,words)

        syntax=analyze_syntax(text,words)

        # The kind for the new entity. This is so all 'Sentences' can be queried.
        kind = "Sentences"
        # Create a key to store into datastore
        key = datastore_client.key(kind)
        # If a key id is not specified then datastore will automatically generate one. For example, if we had:
        # key = datastore_client.key(kind, 'sample_task')
        # instead of the above, then 'sample_task' would be the key id used.

        # Construct the new entity using the key. Set dictionary values for entity
        entity = datastore.Entity(key)
        entity["text"] = text
        entity["timestamp"] = current_datetime
        entity["sentiment"] = overall_sentiment
        entity["entities"] = entities.get("entities")
        entity["entities_esg"] = entities.get("esg")
        #entity["syntax"] = syntax.get("entities")
        entity["syntax_esg"] = syntax.get("esg")

        # Save the new entity to Datastore.
        datastore_client.put(entity)

        result = {}
        result[str(entity.key.id)] = {
            "text": text,
            "timestamp": str(current_datetime),
            "sentiment": overall_sentiment,
            "entities": entities.get("entities"),
            "entities_esg": entities.get("esg"),
            #"syntax": syntax.get("entities"),
            "syntax_esg": syntax.get("esg"),
        }
        return result

    def get(self):
        """
        This GET request will return all the texts and sentiments that have been POSTed previously.
        """
        # Create a Cloud Datastore client.
        datastore_client = datastore.Client()

        # Get the datastore 'kind' which are 'Sentences'
        query = datastore_client.query(kind="Sentences")
        text_entities = list(query.fetch())

        # Parse the data into a dictionary format
        result = {}
        for text_entity in text_entities:
            result[str(text_entity.id)] = {
                "text": str(text_entity["text"]),
                "timestamp": str(text_entity["timestamp"]),
                "sentiment": str(text_entity["sentiment"]),
                "entities": text_entity.get("entities"),
                "entities_esg": text_entity.get("entities_esg"),
                # "syntax": syntax.get("entities"),
                "syntax_esg": text_entity.get("syntax_esg"),
            }

        return result

@api.route("/api/clearSentences")
class Data(Resource):
    def get(self):
        datastore_client = datastore.Client()

        # Get the datastore 'kind' which are 'Sentences'
        query = datastore_client.query(kind="Sentences")

        entities = list(query.fetch())
        for entity in entities:
            datastore_client.delete(entity.key)


@api.route("/api/text")
class Text(Resource):
    def get(self):
        """
        This GET request will return all the texts and sentiments that have been POSTed previously.
        """
        # Create a Cloud Datastore client.
        datastore_client = datastore.Client()

        # Get the datastore 'kind' which are 'Sentences'
        query = datastore_client.query(kind="Sentences")
        text_entities = list(query.fetch())

        # Parse the data into a dictionary format
        result = {}
        for text_entity in text_entities:
            result[str(text_entity.id)] = {
                "text": str(text_entity["text"]),
                "timestamp": str(text_entity["timestamp"]),
                "sentiment": str(text_entity["sentiment"]),
            }

        return result

    @api.expect(parser)
    def post(self):
        """
        This POST request will accept a 'text', analyze the sentiment analysis of the first sentence, store
        the result to datastore as a 'Sentence', and also return the result.
        """
        datastore_client = datastore.Client()

        args = parser.parse_args()
        text = args["text"]

        # Get the sentiment score of the first sentence of the analysis (that's the [0] part)
        sentiment = analyze_text_sentiment(text)[0].get("sentiment score")

        # Assign a label based on the score
        overall_sentiment = "unknown"
        if sentiment > 0:
            overall_sentiment = "positive"
        if sentiment < 0:
            overall_sentiment = "negative"
        if sentiment == 0:
            overall_sentiment = "neutral"

        current_datetime = datetime.now()

        # The kind for the new entity. This is so all 'Sentences' can be queried.
        kind = "Sentences"

        # Create a key to store into datastore
        key = datastore_client.key(kind)
        # If a key id is not specified then datastore will automatically generate one. For example, if we had:
        # key = datastore_client.key(kind, 'sample_task')
        # instead of the above, then 'sample_task' would be the key id used.

        # Construct the new entity using the key. Set dictionary values for entity
        entity = datastore.Entity(key)
        entity["text"] = text
        entity["timestamp"] = current_datetime
        entity["sentiment"] = overall_sentiment

        # Save the new entity to Datastore.
        datastore_client.put(entity)

        result = {}
        result[str(entity.key.id)] = {
            "text": text,
            "timestamp": str(current_datetime),
            "sentiment": overall_sentiment,
        }
        return result


@app.errorhandler(500)
def server_error(e):
    logging.exception("An error occurred during a request.")
    return (
        """
    An internal error occurred: <pre>{}</pre>
    See logs for full stacktrace.
    """.format(
            e
        ),
        500,
    )


def analyze_syntax(text_content,words):
    """
    Analyzing Syntax in a String

    Args:
      text_content The text content to analyze
    """

    client = language_v1.LanguageServiceClient()

    # text_content = 'This is a short sentence.'

    # Available types: PLAIN_TEXT, HTML
    type_ = language_v1.Document.Type.PLAIN_TEXT

    # Optional. If not specified, the language is automatically detected.
    # For list of supported languages:
    # https://cloud.google.com/natural-language/docs/languages
    language = "en"
    document = {"content": text_content, "type_": type_, "language": language}

    # Available values: NONE, UTF8, UTF16, UTF32
    encoding_type = language_v1.EncodingType.UTF8

    response = client.analyze_syntax(request = {'document': document, 'encoding_type': encoding_type})
    # Loop through tokens returned from the API
    entities = []
    esg=[]
    for token in response.tokens:
        # Get the text content of this token. Usually a word or punctuation.
        text = token.text
        print(u"Token text: {}".format(text.content))
        print(
            u"Location of this token in overall document: {}".format(text.begin_offset)
        )
        # Get the part of speech information for this token.
        # Part of speech is defined in:
        # http://www.lrec-conf.org/proceedings/lrec2012/pdf/274_Paper.pdf
        part_of_speech = token.part_of_speech
        # Get the tag, e.g. NOUN, ADJ for Adjective, et al.
        friendly_type = language_v1.PartOfSpeech.Tag(part_of_speech.tag).name
        print(
            u"Part of Speech tag: {}".format(
                friendly_type
            )
        )
        # Get the voice, e.g. ACTIVE or PASSIVE
        print(u"Voice: {}".format(language_v1.PartOfSpeech.Voice(part_of_speech.voice).name))
        # Get the tense, e.g. PAST, FUTURE, PRESENT, et al.
        print(u"Tense: {}".format(language_v1.PartOfSpeech.Tense(part_of_speech.tense).name))
        # See API reference for additional Part of Speech information available
        # Get the lemma of the token. Wikipedia lemma description
        # https://en.wikipedia.org/wiki/Lemma_(morphology)
        print(u"Lemma: {}".format(token.lemma))


        item = {"name": text.content,
                "entitytype":friendly_type
                }
        entities.append(item)
        if (text.content.lower() in words):
            print("We got a match " + text.content.lower())
            esg.append(item)


    return {"entities":entities, "esg":esg}


def analyze_entity_sentiment(text_content,words):
    """
    Analyzing Entity Sentiment in a String

    Args:
      text_content The text content to analyze
    """

    client = language_v1.LanguageServiceClient()

    # text_content = 'Grapes are good. Bananas are bad.'

    # Available types: PLAIN_TEXT, HTML
    type_ = language_v1.types.Document.Type.PLAIN_TEXT

    # Optional. If not specified, the language is automatically detected.
    # For list of supported languages:
    # https://cloud.google.com/natural-language/docs/languages
    language = "en"
    document = {"content": text_content, "type_": type_, "language": language}

    # Available values: NONE, UTF8, UTF16, UTF32
    encoding_type = language_v1.EncodingType.UTF8

    response = client.analyze_entity_sentiment(request = {'document': document, 'encoding_type': encoding_type})
    # Loop through entitites returned from the API
    entities=[]
    esg=[]
    for entity in response.entities:
        print(u"Representative name for the entity: {}".format(entity.name))
        # Get entity type, e.g. PERSON, LOCATION, ADDRESS, NUMBER, et al
        print(u"Entity type: {}".format(language_v1.Entity.Type(entity.type_).name))
        # Get the salience score associated with the entity in the [0, 1.0] range
        print(u"Salience score: {}".format(entity.salience))
        # Get the aggregate sentiment expressed for this entity in the provided document.
        sentiment = entity.sentiment
        print(u"Entity sentiment score: {}".format(sentiment.score))
        print(u"Entity sentiment magnitude: {}".format(sentiment.magnitude))
        # Loop over the metadata associated with entity. For many known entities,
        # the metadata is a Wikipedia URL (wikipedia_url) and Knowledge Graph MID (mid).
        # Some entity types may have additional metadata, e.g. ADDRESS entities
        # may have metadata for the address street_name, postal_code, et al.
        for metadata_name, metadata_value in entity.metadata.items():
            print(u"{} = {}".format(metadata_name, metadata_value))

        # Loop over the mentions of this entity in the input document.
        # The API currently supports proper noun mentions.
        for mention in entity.mentions:
            print(u"Mention text: {}".format(mention.text.content))
            # Get the mention type, e.g. PROPER for proper noun
            print(
                u"Mention type: {}".format(language_v1.EntityMention.Type(mention.type_).name)
            )
        item = {"name": entity.name,
                "entitytype":language_v1.Entity.Type(entity.type_).name,
                "score": entity.sentiment.score,
                "sentiment": getSentiment(entity.sentiment.score),
                }
        entities.append(item)
        if (entity.name.lower() in words):
            print("We got a match " + entity.name.lower())
            esg.append(item)


    return {"entities":entities, "esg":esg}

def analyze_text_sentiment(text):
    """
    This is modified from the Google NLP API documentation found here:
    https://cloud.google.com/natural-language/docs/analyzing-sentiment
    It makes a call to the Google NLP API to retrieve sentiment analysis.
    """
    client = language.LanguageServiceClient()
    document = language.Document(content=text, type_=language.Document.Type.PLAIN_TEXT)

    response = client.analyze_sentiment(document=document)

    # Format the results as a dictionary
    sentiment = response.document_sentiment
    results = dict(
        text=text,
        score=f"{sentiment.score:.1%}",
        magnitude=f"{sentiment.magnitude:.1%}",
    )

    # Print the results for observation
    for k, v in results.items():
        print(f"{k:10}: {v}")

    # Get sentiment for all sentences in the document
    sentence_sentiment = []
    for sentence in response.sentences:
        item = {}
        item["text"] = sentence.text.content
        item["sentiment score"] = sentence.sentiment.score
        item["sentiment magnitude"] = sentence.sentiment.magnitude
        sentence_sentiment.append(item)

    return sentence_sentiment

def getSentiment(sentiment):
    overall_sentiment = "unknown"
    if sentiment > 0:
        overall_sentiment = "positive"
    if sentiment < 0:
        overall_sentiment = "negative"
    if sentiment == 0:
        overall_sentiment = "neutral"
    return overall_sentiment


if __name__ == "__main__":
    # This is used when running locally. Gunicorn is used to run the
    # application on Google App Engine. See entrypoint in app.yaml.
    app.run(host="127.0.0.1", port=8080, debug=True)
