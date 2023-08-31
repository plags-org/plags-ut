'use strict';

class SubmissionEvaluationLoader extends React.Component {
  // prop: gqlServerUrl string MAYBE TODO: replace by `gqlClient`
  // prop: organizationName string
  // prop: courseName string
  // prop: submissionEb64 string
  constructor(props) {
    super(props);
    this.state = {
      organizationName: this.props.organizationName,
      courseName: this.props.courseName,
      submissionEb64: this.props.submissionEb64,
      evaluationProgressPercent: 0,
    };
    // console.log(this.state); // for DEBUG
    this.subscribeEvaluationProgress();
  }

  subscribeEvaluationProgress() {
    // URL を環境ごとに変える（props を経由する）
    const gqlServerUrl = this.props.gqlServerUrl;
    const gqlClient = graphqlWs.createClient({ url: gqlServerUrl });

    const subscriptionQuery = `subscription {
      submissionEvaluation (
        organizationName: "${this.state.organizationName}",
        courseName: "${this.state.courseName}",
        submissionEb64: "${this.state.submissionEb64}"
      ) {
        progressPercent
      }
    }`;
    // console.log(subscriptionQuery);

    (async () => {
      const onNext = (event) => {
        const evaluationProgressPercent = event.data.submissionEvaluation.progressPercent;
        if (evaluationProgressPercent === 100) {
          // animation を待つ
          setTimeout(() => location.reload(true), 500);
        }
        this.setState({ evaluationProgressPercent });
      };

      let unsubscribe = () => {
        console.log("unsubscribe called");
        /* complete the subscription */
      };

      await new Promise((resolve, reject) => {
        unsubscribe = gqlClient.subscribe(
          {
            query: subscriptionQuery,
          },
          {
            next: onNext,
            error: reject,
            complete: resolve,
          },
        );
      });
    })();
  }

  render() {
    return (
      <div>
        <ReactBootstrap.ProgressBar animated now={this.state.evaluationProgressPercent} />
      </div>
    );
  }
}

function mountSubmissionEvaluationLoader(
  { targetDomId, props }
) {
  const domContainer = document.getElementById(targetDomId);
  ReactDOM.createRoot(domContainer).render(<
    SubmissionEvaluationLoader
    {...props}
  />);
}
