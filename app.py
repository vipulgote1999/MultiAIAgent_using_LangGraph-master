from flask import Flask, render_template, request
from workflow import app as langgraph_app
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

flask_app = Flask(__name__)

@flask_app.route("/")
def index():
    # When the page first loads, no results are passed
    return render_template("index.html", results=None)

@flask_app.route("/ask", methods=["POST"])
def ask():
    try:
        # Get the question from the form submission
        user_question = request.form.get("question", "")
        inputs = {"question": user_question}

        # Process the question and get the response
        results = []
        for output in langgraph_app.stream(inputs):
            for key, value in output.items():
                if key == "retrieve":
                    documents = value['documents'][0].metadata['description']
                else:
                    documents = value['documents'].page_content.split('Summary: ')[1]
                results.append({"user_query": user_question, "node": key, "documents": documents})

        # Render the index page again, passing the results to display the response
        return render_template("index.html", results=results)
    
    except Exception as e:
        # Handle the error and show it in the UI
        return render_template("index.html", results=[{"node": "Error", "documents": str(e)}])

if __name__ == "__main__":
    flask_app.run(debug=True, host="0.0.0.0", port=5000)
