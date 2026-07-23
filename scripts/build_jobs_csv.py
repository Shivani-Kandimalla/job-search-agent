"""
One-time generator for data/jobs.csv.

The 23 postings below were manually collected (via web search + reading the
real posting pages) on 2026-07-23 from real, currently-live job postings at
real companies. This script only handles the CSV formatting/escaping; no
scraping code touches the job sites themselves.

Run: python scripts/build_jobs_csv.py
"""

import csv
import os

JOBS = [
    {
        "job_id": "J01",
        "title": "Machine Learning Engineer, Distributed Data Systems (Robotics)",
        "company": "OpenAI",
        "industry_domain": "AI Research / Robotics",
        "location": "San Francisco, CA (Hybrid, 3 days/week)",
        "required_skills": "Python, distributed systems, data pipelines, streaming infrastructure, machine learning infrastructure, Kubernetes-style orchestration",
        "years_experience": "3+",
        "description": (
            "Design, build, and maintain data infrastructure systems such as distributed compute, "
            "data orchestration, distributed storage, and streaming infrastructure for large-scale "
            "multimodal training and evaluation.\n"
            "Manage distributed data pipelines that power OpenAI's rapid research iteration cycles.\n"
            "Collaborate closely with researchers to translate modeling requirements into robust, "
            "production-grade systems.\n"
            "Harden, optimize, and maintain critical data infrastructure that scales by orders of "
            "magnitude while remaining reliable and efficient.\n"
            "Ensure the data platform can support rapid growth in dataset size and training throughput.\n"
            "Qualifications: strong experience with distributed systems and large-scale infrastructure; "
            "detail-oriented with rigor in building reliable systems; excellent software engineering "
            "fundamentals; comfortable with ambiguity and fast-changing priorities; strong interest in "
            "data-heavy ML systems work rather than pure modeling."
        ),
        "company_details": (
            "OpenAI is an AI research and deployment company whose mission is to ensure that "
            "artificial general intelligence benefits all of humanity. It builds and deploys "
            "large-scale AI systems including the GPT model family."
        ),
        "url": "https://openai.com/careers/machine-learning-engineer-distributed-data-systems-robotics-san-francisco/",
    },
    {
        "job_id": "J02",
        "title": "AI/ML Engineer - Model Inference",
        "company": "General Motors",
        "industry_domain": "Automotive / Autonomous Systems",
        "location": "Sunnyvale, CA",
        "required_skills": "Python, computer vision, multimodal models, inference frameworks, embeddings, retrieval systems, ML pipeline evaluation",
        "years_experience": "3+",
        "description": (
            "Build the data processing, featurization, and inference foundations that power scalable "
            "world understanding for autonomous and driver-assist systems.\n"
            "Design, build, and productionize data processing and featurization pipelines for "
            "large-scale multimodal data.\n"
            "Improve inference frameworks for computer vision and multimodal models with a focus on "
            "reliability, extensibility, and operational simplicity.\n"
            "Drive scalability and cost efficiency across the end-to-end pipeline, including compute "
            "utilization, throughput, storage, and query performance.\n"
            "Work closely with partners across machine learning and platform teams.\n"
            "Evaluate machine learning systems using clear metrics, experiments, and regression "
            "safeguards.\n"
            "Qualifications: BS/MS/PhD in Computer Science, Electrical Engineering, Robotics, or "
            "equivalent practical experience; experience building production data or ML pipelines at "
            "scale; experience with featurization, embedding, inference, or retrieval systems for "
            "vision or multimodal workloads."
        ),
        "company_details": (
            "General Motors is a major American automotive manufacturer investing heavily in "
            "software-defined vehicles, autonomous driving, and AI-powered driver-assistance systems."
        ),
        "url": "https://search-careers.gm.com/en/jobs/jr-202613719/ai-ml-engineer-model-inference/",
    },
    {
        "job_id": "J03",
        "title": "Senior Machine Learning Engineer, Payments",
        "company": "Airbnb",
        "industry_domain": "Travel & Hospitality / Payments",
        "location": "US - Remote Eligible",
        "required_skills": "LLM-powered workflows, RLHF, real-time fraud detection systems, ML orchestration frameworks, model governance, online/offline testing",
        "years_experience": "5+",
        "description": (
            "Transform bold AI innovation - LLM-powered workflows, real-time fraud defenses, and "
            "hyper-personalized checkout flows - into production systems for Airbnb's payments "
            "experience.\n"
            "Architect and own end-to-end solutions at global scale.\n"
            "Partner closely with product, software, and operations teams to turn complex requirements "
            "into elegant, latency-first services.\n"
            "Set the technical standard for model governance, continuous learning, and engineering "
            "excellence across the payments ecosystem.\n"
            "Shape the company's broader AI strategy for trust and safety in payments.\n"
            "Qualifications: 5+ years of industry experience in applied AI/ML (MS or PhD a plus); "
            "mastery of modern AI techniques including RLHF and hallucination mitigation; hands-on "
            "experience with at least three ML orchestration/serving tools; demonstrated success "
            "designing, deploying, and scaling AI systems with measurable business impact."
        ),
        "company_details": (
            "Airbnb operates a global online marketplace for lodging and travel experiences, "
            "connecting hosts and guests in over 220 countries and regions."
        ),
        "url": "https://careers.airbnb.com/positions/7755758/",
    },
    {
        "job_id": "J04",
        "title": "Senior Software Machine Learning Engineer",
        "company": "Teradyne",
        "industry_domain": "Semiconductor / Manufacturing",
        "location": "North Reading, MA",
        "required_skills": "Python, LLM fine-tuning, reinforcement learning (PPO, actor-critic), time-series analysis, computer vision, MLOps, model deployment, LangChain",
        "years_experience": "5+",
        "description": (
            "Serve as Teradyne's highest individual-contributor technical authority in ML, owning "
            "end-to-end technical excellence of the company's machine learning systems.\n"
            "Define modeling standards and set the engineering bar for the entire ML team.\n"
            "Take personal ownership of the most complex and highest-impact ML problems, spanning "
            "time-series analysis of semiconductor parametric test data, computer vision for defect "
            "detection, adaptive test optimization, and applied LLM systems.\n"
            "Mentor junior engineers and act as the go-to technical voice for hard ML problems.\n"
            "Qualifications: 5+ years of experience in machine learning, applied AI, or related fields; "
            "hands-on experience fine-tuning large language models; experience with reinforcement "
            "learning methods; strong systems and Python skills; experience building production ML "
            "systems including MLOps, monitoring, and deployment; familiarity with LangChain and "
            "reasoning-driven workflow design."
        ),
        "company_details": (
            "Teradyne designs and manufactures automated test equipment used across the semiconductor "
            "and electronics manufacturing industry, serving customers who build chips and devices."
        ),
        "url": "https://jobs.teradyne.com/Teradyne/job/North-Reading-Senior-Software-Machine-Learning-Engineer-%28Teradyne%2C-North-Reading%2C-MA%29-MA/1408695700/",
    },
    {
        "job_id": "J05",
        "title": "Machine Learning Engineer II, Special Projects",
        "company": "Amazon",
        "industry_domain": "Technology / E-commerce",
        "location": "Seattle, WA",
        "required_skills": "Python, Java, software architecture and design patterns, ML systems, data engineering, distributed systems reliability",
        "years_experience": "3+",
        "description": (
            "Join an Amazon Special Projects team tackling ambitious, undefined problems at scale.\n"
            "Leverage machine learning to build scalable, highly performant AI systems.\n"
            "Collaborate closely with Applied Scientists on modeling experiments and prototypes.\n"
            "Develop and maintain the key infrastructure needed for building and evaluating ML "
            "solutions.\n"
            "Develop tools for data engineering and efficient utilization of large compute resources.\n"
            "Operate in a fast-paced, Agile environment with little bureaucracy.\n"
            "Qualifications: 3+ years of non-internship professional software development experience; "
            "3+ years of experience with design or architecture (design patterns, reliability, and "
            "scaling) of new and existing systems; strong programming skills in at least one language; "
            "comfort with ambiguity and rapidly evolving priorities."
        ),
        "company_details": (
            "Amazon is a global technology company operating one of the world's largest e-commerce "
            "platforms alongside AWS, its cloud computing division, and a growing portfolio of "
            "consumer AI products."
        ),
        "url": "https://www.amazon.jobs/en/jobs/3121713/machine-learning-engineer-ii-special-projects",
    },
    {
        "job_id": "J06",
        "title": "Research Scientist",
        "company": "OpenAI",
        "industry_domain": "AI Research",
        "location": "San Francisco, CA",
        "required_skills": "Deep learning research, experiment design, large-scale model training, independent research agenda ownership, published research or equivalent track record",
        "years_experience": "3+ (research track record required)",
        "description": (
            "Develop innovative machine learning techniques and advance the research agenda of the "
            "team, while collaborating with peers across the organization.\n"
            "Discover simple, generalizable ideas that work well at large scale as part of a broader "
            "unifying research vision.\n"
            "Own and pursue a research agenda, including choosing impactful research problems and "
            "autonomously carrying out long-running projects.\n"
            "Qualifications: track record of coming up with new ideas or improving existing ideas in "
            "machine learning, demonstrated by first-author publications or comparable projects; past "
            "experience creating high-performance implementations of deep learning algorithms; "
            "genuine interest in the societal impacts of AI technology."
        ),
        "company_details": (
            "OpenAI is an AI research and deployment company whose mission is to ensure that "
            "artificial general intelligence benefits all of humanity."
        ),
        "url": "https://openai.com/careers/research-scientist-san-francisco/",
    },
    {
        "job_id": "J07",
        "title": "AI Research Scientist",
        "company": "webAI",
        "industry_domain": "AI Research / On-device AI",
        "location": "Remote",
        "required_skills": "Python, PyTorch, TensorFlow, JAX, transformers, CNNs, diffusion models, quantization, distillation, pruning, federated learning",
        "years_experience": "4+",
        "description": (
            "Contribute to webAI's development of next-generation AI models and systems.\n"
            "Design, train, evaluate, and optimize cutting-edge machine learning models including "
            "large language models, multimodal architectures, and on-device inference systems.\n"
            "Work closely with research leadership, applied AI teams, and platform engineering to "
            "translate scientific innovation into real-world impact.\n"
            "Develop and evaluate benchmarks for on-device and edge inference performance.\n"
            "Qualifications: 4+ years of experience (graduate research counts) in ML research, AI "
            "model development, or related fields; strong expertise in deep learning architectures "
            "including transformers, CNNs, RNNs, and diffusion models; hands-on experience training "
            "and fine-tuning large-scale models; deep understanding of optimization techniques "
            "including quantization, distillation, pruning, and hardware-aware training."
        ),
        "company_details": (
            "webAI builds next-generation on-device AI models and systems, focused on bringing "
            "efficient multimodal AI inference directly onto edge hardware."
        ),
        "url": "https://homebased.totalh.net/job/ai-research-scientist-5",
    },
    {
        "job_id": "J08",
        "title": "Staff AI Research Scientist",
        "company": "Writer",
        "industry_domain": "Enterprise Generative AI",
        "location": "San Francisco, CA / New York, NY",
        "required_skills": "Python, PyTorch, JAX, SFT, RLHF, RLAIF, DPO, GRPO, agentic system design and evaluation, large-scale distributed training",
        "years_experience": "7+",
        "description": (
            "Lead post-training research for Writer's enterprise generative AI platform, reporting to "
            "the VP of AI Research.\n"
            "Design and execute large-scale post-training experiments using supervised fine-tuning, "
            "RLHF, RLAIF, DPO, and emerging alignment techniques, with a focus on multi-step reasoning, "
            "planning, and tool use in agentic workflows.\n"
            "Develop scalable data pipelines that generate high-quality training data, including "
            "synthetic data generation and adversarial dataset construction.\n"
            "Qualifications: 7+ years of hands-on ML research experience with deep expertise in LLM "
            "pre-training and post-training; expert-level knowledge of SFT, RLHF, RLAIF, DPO, and GRPO; "
            "strong command of Python and PyTorch/JAX; meaningful publication record at competitive "
            "ML/AI venues; hands-on experience designing or evaluating agentic systems; PhD in CS, ML, "
            "NLP, or equivalent demonstrated research experience."
        ),
        "company_details": (
            "Writer builds an enterprise generative AI platform that helps large organizations create "
            "content and automate workflows using custom large language models."
        ),
        "url": "https://underprompt.com/jobs/staff-ai-research-scientist-writer",
    },
    {
        "job_id": "J09",
        "title": "Fundamental AI Research Scientist",
        "company": "AstraZeneca",
        "industry_domain": "Pharmaceutical / Healthcare Research",
        "location": "Toronto (Mississauga), Ontario",
        "required_skills": "Python, PyTorch, TensorFlow, causal inference, Bayesian optimization, natural language processing, probabilistic programming, experimental design",
        "years_experience": "3+ (PhD-level research experience expected)",
        "description": (
            "Conduct fundamental AI research and development with hands-on ability to implement AI/ML "
            "techniques based on publications or developed entirely in-house.\n"
            "Apply rigorous scientific methodology to identify and create ML techniques and required "
            "training data, develop AI/ML architectures and training algorithms, analyze and fine-tune "
            "experimental results, and implement and scale training and inference engineering "
            "frameworks.\n"
            "Validate hypotheses across areas such as multi-agent systems, causal inference, Bayesian "
            "optimization, deep learning, reinforcement learning, and natural language processing.\n"
            "Qualifications: fundamental research experience with hands-on practical implementation "
            "ability; algorithmic development and programming experience in Python or similar "
            "languages, with deep learning toolkits (PyTorch, TensorFlow); expertise in at least one "
            "advanced ML research area."
        ),
        "company_details": (
            "AstraZeneca is a global biopharmaceutical company focused on the discovery, development, "
            "and commercialization of prescription medicines, increasingly leveraging AI in drug "
            "discovery research."
        ),
        "url": "https://careers.astrazeneca.com/job/mississauga/fundamental-ai-research-scientist-toronto-ontario/7684/88572962192",
    },
    {
        "job_id": "J10",
        "title": "Data Scientist - Remote",
        "company": "UnitedHealth Group",
        "industry_domain": "Healthcare / Insurance",
        "location": "Minnetonka, MN (Remote)",
        "required_skills": "Python, Scala, SQL, Databricks, Spark, LLM/GenAI, RAG pipelines, vector databases, LangChain, Azure OpenAI, CI/CD (Git, GitHub Actions, Terraform)",
        "years_experience": "5+",
        "description": (
            "Serve in a senior, hands-on AI/ML engineering position focused on building, enhancing, "
            "and integrating machine learning and generative AI solutions within Databricks.\n"
            "Own end-to-end ML model development: data preparation, feature creation, training, and "
            "evaluation.\n"
            "Build custom embedding models, RAG pipelines, and semantic search using vector databases.\n"
            "Use LangChain for agentic workflows involving tools, agents, and memory.\n"
            "Work with actuarial, risk, and forecasting models for healthcare claims data.\n"
            "Qualifications: Bachelor's/Master's in CS, Engineering, Mathematics/Statistics, or related "
            "field; 5+ years as a Data Scientist; 5+ years of Python, Scala, SQL; 3+ years of "
            "Databricks/Spark; 2+ years of LLM and GenAI experience; experience with Azure cloud, "
            "CI/CD, and healthcare claims data preferred."
        ),
        "company_details": (
            "UnitedHealth Group is a diversified healthcare and health insurance company operating "
            "one of the largest health benefits and care delivery platforms in the United States."
        ),
        "url": "https://careers.unitedhealthgroup.com/en/job/minnetonka/data-scientist-remote/34088/95342534368",
    },
    {
        "job_id": "J11",
        "title": "Staff Data Scientist (SME: Healthcare Financial Risk & Underwriting)",
        "company": "Prealize Health",
        "industry_domain": "Healthcare / Predictive Analytics",
        "location": "Remote",
        "required_skills": "Machine learning, actuarial modeling, healthcare risk adjustment, underwriting analytics, Python, SQL, predictive modeling",
        "years_experience": "6+",
        "description": (
            "Serve as the primary subject-matter expert for healthcare financial risk and underwriting "
            "modeling, acting as the technical authority for the company's most critical modeling "
            "domains.\n"
            "Bridge the gap between complex actuarial needs and cutting-edge machine learning.\n"
            "Define the technical roadmap to scale predictive models for risk adjustment and "
            "underwriting.\n"
            "Lead the evolution of predictive models that power the company's underwriting product.\n"
            "Qualifications: deep experience in healthcare predictive analytics and actuarial risk "
            "modeling; strong machine learning engineering skills; ability to operate as a strategic, "
            "high-impact technical leader for a specialized modeling domain."
        ),
        "company_details": (
            "Prealize Health is a predictive analytics company that leverages machine learning and "
            "clinical expertise to help patients obtain better care sooner, focusing on preventive, "
            "proactive healthcare."
        ),
        "url": "https://hirenixa.10001mb.com/job/staff-data-scientist-sme-healthcare-financial-risk-underwriting-2",
    },
    {
        "job_id": "J12",
        "title": "Senior Data Scientist, Products",
        "company": "CVS Caremark",
        "industry_domain": "Healthcare / Insurance (PBM)",
        "location": "Remote (US)",
        "required_skills": "Python, SQL, PySpark, Databricks, Snowflake, regression, classification, clustering, time-series forecasting, MLflow, Vertex AI/SageMaker",
        "years_experience": "5+",
        "description": (
            "Lead a workstream within Caremark's sales and underwriting analytics portfolio, owning "
            "end-to-end delivery as a senior individual contributor.\n"
            "Own multiple concurrent projects across model development, strategic analysis, and "
            "analytics product delivery, framing business questions and presenting findings to senior "
            "stakeholders.\n"
            "Set technical direction for the workstream and mentor junior data scientists.\n"
            "Partner directly with business leaders across sales, underwriting, and finance to turn "
            "analysis into action.\n"
            "Qualifications: 5+ years of data science experience with at least 2 years in financial "
            "services, insurance, healthcare, or PBM; production-grade Python and advanced SQL; "
            "proficiency with PySpark, Databricks, Snowflake, or distributed computing; strong "
            "fundamentals across regression, classification, clustering, time-series forecasting, and "
            "experiment design."
        ),
        "company_details": (
            "CVS Caremark is the pharmacy benefit management (PBM) division of CVS Health, managing "
            "prescription drug benefits for large employers, health plans, and government programs."
        ),
        "url": "https://hiresub.infinityfree.me/job/senior-data-scientist-products-5062110",
    },
    {
        "job_id": "J13",
        "title": "Data Scientist - Medicare/Medicaid Claims Data",
        "company": "Flexgen Life Sciences",
        "industry_domain": "Healthcare / Life Sciences",
        "location": "Remote (US)",
        "required_skills": "SAS, SQL, health economics, real-world evidence analysis, Medicare/Medicaid claims analytics, statistical modeling",
        "years_experience": "3+",
        "description": (
            "Join the Strategic Analytics, Value, and Economics team to leverage advanced data science "
            "and health economics methods that shape access to life-saving therapies.\n"
            "Work with rich, real-world healthcare data including Medicare and Medicaid claims to "
            "uncover insights that directly inform policy, pricing, and patient access decisions.\n"
            "Design and execute analyses in Medicare and Medicaid healthcare claims data.\n"
            "Prepare client-facing deliverables including presentations summarizing health economics "
            "and outcomes research (HEOR) findings.\n"
            "Qualifications: Master's or PhD in Data Science, Biostatistics, Health Economics, "
            "Epidemiology, Public Health, Computer Science, or a related quantitative field; at least "
            "3 years of professional experience with SAS, SQL, or similar tools applying data science "
            "in healthcare, HEOR, or life sciences; demonstrated experience with large-scale health "
            "data analysis (claims, EHR, registry, or clinical trial data)."
        ),
        "company_details": (
            "This life sciences analytics group partners with pharmaceutical and biotech companies to "
            "apply real-world evidence and health economics research to improve patient access to "
            "treatments."
        ),
        "url": "https://flexgen.zya.me/job/data-scientist-medicare-medicaid-claims-data",
    },
    {
        "job_id": "J14",
        "title": "MLOps Engineer, Machine Learning Engineer (Remote)",
        "company": "Experian Health",
        "industry_domain": "Healthcare / Credit & Data Services",
        "location": "Remote (US)",
        "required_skills": "Python, AWS SageMaker, Lambda, Step Functions, Docker, Kubernetes (EKS), MLflow, TensorFlow Serving, Kubeflow, Terraform, CloudFormation",
        "years_experience": "3+",
        "description": (
            "Build and scale machine learning solutions addressing critical challenges in the "
            "healthcare revenue cycle.\n"
            "Operationalize ML models and maintain scalable, secure ML infrastructure on AWS.\n"
            "Develop scalable MLOps pipelines for model training, validation, deployment, and "
            "monitoring using AWS services.\n"
            "Collaborate with data scientists to productionize ML models and ensure reproducibility, "
            "versioning, and traceability.\n"
            "Monitor model performance and data drift in production, implementing automated "
            "retraining and alerting.\n"
            "Qualifications: Bachelor's degree in Computer Science, Engineering, Data Science, or "
            "related field; 3+ years' experience in MLOps, DevOps, or ML engineering roles; 3+ years' "
            "experience with AWS ML services; proficiency with Docker and Kubernetes/EKS; experience "
            "with MLflow, TensorFlow Serving, or Kubeflow; experience in the healthcare domain, "
            "especially claims or EHR data, is a plus."
        ),
        "company_details": (
            "Experian Health is the healthcare division of Experian, providing data-driven identity, "
            "revenue cycle, and care management solutions to hospitals and health systems."
        ),
        "url": "https://builtin.com/job/mlops-engineer-machine-learning-engineer-remote/8103598",
    },
    {
        "job_id": "J15",
        "title": "Senior MLOps Engineer",
        "company": "IDT Corporation",
        "industry_domain": "Telecom / Fintech (Cross-Border Payments)",
        "location": "Remote",
        "required_skills": "Kubernetes, GitOps, MLflow, ClearML, Dagster, Airflow, Kserve, Evidently, real-time model serving, RBAC and data lineage",
        "years_experience": "7+ (3+ hands-on MLOps)",
        "description": (
            "Act as the technical bridge between Modelers (Data Scientists) and DevOps/Infrastructure "
            "teams for a decisioning platform that reduces fraud in cross-border transactions.\n"
            "Build and maintain a seamless platform for real-time model deployment and serving.\n"
            "Design and own the internal MLOps platform from scratch, focusing on production Kubernetes "
            "clusters, automated GitOps pipelines, and scalable model registries.\n"
            "Implement high-performance ML pipelines for real-time inference, model evaluation, "
            "rollouts, and automated rollbacks.\n"
            "Drive technical standards for production model monitoring, tracking data/concept drift, "
            "and ensuring data lineage and security.\n"
            "Qualifications: 7+ years of overall experience in Infrastructure or Platform Engineering "
            "with 3+ years focused on hands-on production MLOps architectures; strong Kubernetes "
            "expertise; hands-on experience with model serving/orchestration tools; practical "
            "experience operationalizing models for low-latency, real-time production serving."
        ),
        "company_details": (
            "IDT Corporation provides international communications and fintech services, including "
            "cross-border payment and remittance platforms, helping reduce fraud and improve "
            "transaction reliability."
        ),
        "url": "https://jobs.lever.co/idt/9179d3e9-344c-4e63-afbd-727f849fac54",
    },
    {
        "job_id": "J16",
        "title": "MLOps Engineer - Credit Risk and Fraud Platform (Banking)",
        "company": "International Banking Platform (via Homebased)",
        "industry_domain": "Banking / Fintech",
        "location": "Remote",
        "required_skills": "Python, Docker, Kubernetes, MLflow, CI/CD pipelines, Azure or AWS, LangChain, LangGraph, model governance and regulatory documentation",
        "years_experience": "4+",
        "description": (
            "Join a large-scale decision intelligence platform supporting credit risk assessment and "
            "fraud prevention within an international banking environment.\n"
            "Build and maintain CI/CD pipelines for machine learning models in a production-critical, "
            "regulated environment.\n"
            "Operationalize model lifecycle processes including versioning, promotion, and rollback.\n"
            "Deploy and operate LangChain and LangGraph based reasoning services layered on top of "
            "core ML outputs.\n"
            "Implement monitoring for model performance, drift detection, and runtime failures.\n"
            "Ensure traceability, auditability, and compliance readiness in a regulated environment.\n"
            "Qualifications: strong hands-on experience in MLOps or ML platform engineering; solid "
            "Python skills; experience with Docker and Kubernetes in production; practical experience "
            "with MLflow or similar tools; experience with Azure or AWS; ability to operate in "
            "regulated or compliance-heavy environments."
        ),
        "company_details": (
            "This platform serves an international banking group's credit risk and fraud prevention "
            "operations, combining machine learning, high-volume data processing, and GenAI "
            "orchestration embedded directly into live banking systems."
        ),
        "url": "https://homebased.totalh.net/job/mlops-engineer-credit-risk-and-fraud-platform-banking",
    },
    {
        "job_id": "J17",
        "title": "Staff Machine Learning Engineer - NLP/Computer Vision",
        "company": "Enterprise Data Extraction Platform (via hirist.tech)",
        "industry_domain": "Enterprise Software / Data Extraction",
        "location": "Remote / Hybrid",
        "required_skills": "PyTorch, TensorFlow, OpenCV, scikit-learn, LLMs, VLMs, OCR and text extraction, AWS SageMaker",
        "years_experience": "6+",
        "description": (
            "Design and implement machine learning, deep learning, classical computer vision, and NLP "
            "algorithms focused on data extraction.\n"
            "Research and support the deployment of advanced algorithms into production systems.\n"
            "Develop, evolve, and support production-quality code, deploying models as AWS SageMaker "
            "endpoints or directly onto devices.\n"
            "Stay current with advancements in deep learning, computer vision, and NLP.\n"
            "Work collaboratively with engineers and product managers in an Agile environment.\n"
            "Qualifications: Bachelor's or Master's in Computer Science, Data Science, Machine "
            "Learning, or related field; 6+ years of commercial experience in computer vision, ML, or "
            "related area; proficiency in computer vision, deep learning, and NLP techniques; hands-on "
            "experience with PyTorch or TensorFlow, OpenCV, scikit-learn; demonstrated experience "
            "monitoring and maintaining ML models in production."
        ),
        "company_details": (
            "This platform helps enterprises extract structured information from unstructured "
            "documents and images at scale, combining classical computer vision and modern LLM/VLM "
            "techniques."
        ),
        "url": "https://www.hirist.tech/j/staff-machine-learning-engineer-nlp-computer-vision-1649338",
    },
    {
        "job_id": "J18",
        "title": "AI Engineer: Computer Vision, LLMs & ML",
        "company": "Flexgen Construction Technology",
        "industry_domain": "Construction Technology",
        "location": "Remote",
        "required_skills": "Python, PyTorch, TensorFlow, JAX, RAG, embeddings, vector databases, computer vision (YOLO, Segment Anything), LangChain, LlamaIndex",
        "years_experience": "2-3+",
        "description": (
            "Serve as the founding AI engineer tackling problems with no off-the-shelf answers on "
            "construction job sites.\n"
            "Build RAG systems that understand construction terminology and domain-specific language.\n"
            "Deploy computer vision that detects safety violations from real-world job-site photos "
            "taken in poor lighting conditions.\n"
            "Create AI assistants that answer project-status questions by reasoning across blueprints, "
            "contracts, RFIs, and daily photo logs.\n"
            "Design real-time progress tracking that works reliably even with poor site connectivity.\n"
            "Qualifications: recent graduate from a top AI program or 2-3+ years building production "
            "ML systems; shipped at least one LLM-based application used by real users; experience "
            "with RAG, embeddings, and vector databases; strong Python skills plus PyTorch, TensorFlow, "
            "or JAX; computer vision experience (YOLO, Segment Anything) is a plus."
        ),
        "company_details": (
            "This construction-technology startup builds domain-aware AI tools that make construction "
            "sites safer and more efficient, applying computer vision and LLMs to real-world "
            "job-site data."
        ),
        "url": "https://flexgen.zya.me/job/ai-engineer-computer-vision-llms-ml",
    },
    {
        "job_id": "J19",
        "title": "Senior AI/ML Engineer - Multimodal Content Intelligence",
        "company": "Global Content Platform (via NLP People)",
        "industry_domain": "Media / Content Recommendation",
        "location": "Remote / Hybrid",
        "required_skills": "PyTorch, TensorFlow, JAX, multimodal learning, computer vision, NLP, recommendation systems, MLLMs, VLMs, representation learning",
        "years_experience": "5+",
        "description": (
            "Develop advanced multimodal understanding solutions across video, audio, image, and text "
            "using state-of-the-art Multimodal Large Language Models (MLLMs).\n"
            "Develop and optimize multimodal AI frameworks focused on semantic understanding, "
            "narrative reasoning, and high-level content interpretation.\n"
            "Build and deploy advanced AI models combining video, audio, image, and text signals.\n"
            "Develop scalable, low-latency AI systems suitable for high-concurrency production "
            "environments.\n"
            "Collaborate with recommendation, search, and platform teams to integrate content "
            "intelligence signals into production pipelines.\n"
            "Qualifications: Master's or PhD in Computer Science, AI, ML, or related field; 5+ years of "
            "commercial AI/ML research or advanced ML engineering experience; strong experience in at "
            "least two of: multimodal learning, computer vision, NLP, recommendation systems, "
            "representation learning; hands-on experience with PyTorch, TensorFlow, or JAX; experience "
            "deploying ML models into large-scale production environments."
        ),
        "company_details": (
            "This global technology organization develops next-generation AI-driven content "
            "intelligence and recommendation systems for video, audio, image, and text content at "
            "scale."
        ),
        "url": "https://nlppeople.com/job/senior-ai-ml-engineer-multimodal-content-intelligence-mllms-computer-vision-nlp-2/",
    },
    {
        "job_id": "J20",
        "title": "AI Product Manager",
        "company": "Marks & Spencer",
        "industry_domain": "Retail",
        "location": "London, UK",
        "required_skills": "Product management, AI/ML fundamentals, discovery and experimentation, cross-functional leadership, stakeholder management",
        "years_experience": "5+",
        "description": (
            "Play a pivotal role in turning the potential of AI into real, scalable value for Marks "
            "& Spencer within the AI Accelerator team.\n"
            "Work at the intersection of business, technology, and delivery to identify, prioritize, "
            "and shape AI-enabled products that measurably improve customer and colleague "
            "experiences.\n"
            "Lead discovery, experimentation, and delivery, ensuring AI solutions are grounded in real "
            "problems and designed for adoption.\n"
            "Partner with AI engineers, data scientists, and designers to shape AI solutions that are "
            "valuable, feasible, usable, and ready to scale.\n"
            "Own the product lifecycle end to end, from problem definition through launch, adoption, "
            "and value realization.\n"
            "Qualifications: experienced product manager with a strong track record of shaping and "
            "delivering AI-enabled digital products that create measurable commercial and operational "
            "impact; ability to partner closely with engineering and data science teams; strong bias "
            "for pace and learning."
        ),
        "company_details": (
            "Marks & Spencer (M&S) is a major British multinational retailer known for clothing, home "
            "goods, and food products, investing in AI to improve customer and colleague experiences."
        ),
        "url": "https://jobs.marksandspencer.com/job-search/digital-tech/london-greater-london/ai-product-manager/300007413078490",
    },
    {
        "job_id": "J21",
        "title": "Sr Applied Data Scientist - Search and Browse (Applied ML, NLP, LLMs)",
        "company": "Target Corporation",
        "industry_domain": "Retail / E-commerce",
        "location": "Sunnyvale, CA (Hybrid)",
        "required_skills": "Embeddings, retrieval and ranking models, transformers, NLP, vector search, GenAI/RAG systems, query understanding",
        "years_experience": "3+",
        "description": (
            "Develop and deploy scalable ML models for search ranking, browse personalization, "
            "semantic retrieval, and query understanding systems.\n"
            "Design and execute experiments to improve search relevance and personalization quality.\n"
            "Apply modern ML techniques including embeddings, retrieval/ranking models, transformers, "
            "NLP, vector search, and GenAI/RAG systems.\n"
            "Improve query understanding, catalog understanding, semantic retrieval, and long-tail "
            "search relevance across large retail catalogs.\n"
            "Qualifications: 3+ years of industry experience in Machine Learning, Data Science, "
            "Search, NLP, Personalization, or related ML systems; exceptional experience with "
            "retrieval/ranking systems, semantic search, NLP, or vector search; hybrid work "
            "arrangement based at Target's Sunnyvale or Minnesota locations."
        ),
        "company_details": (
            "Target Corporation is a major American retail chain operating both physical stores and a "
            "large e-commerce platform, investing heavily in AI-driven search and personalization."
        ),
        "url": "https://www.dice.com/job-detail/daab4b90-ec4f-4b0c-8b85-6540c9ccae03",
    },
    {
        "job_id": "J22",
        "title": "Senior Applied AI/ML Scientist - Retailer Growth",
        "company": "Faire",
        "industry_domain": "Wholesale E-commerce Marketplace",
        "location": "San Francisco, CA (Remote-friendly)",
        "required_skills": "Machine learning, LTV modeling, NLP, LLMs, causal ML, bidding optimization, recommender systems, reinforcement learning",
        "years_experience": "3+",
        "description": (
            "Drive data science vision, strategy, and execution within the Retailer Growth team, using "
            "AI/ML solutions to activate and engage more retailers on the platform.\n"
            "Develop algorithmic solutions for notification and recommender systems, advertising "
            "attribution, and lifetime-value (LTV) predictions.\n"
            "Work on paid marketing optimization, from bidding optimization and search keyword "
            "intelligence to smart audience targeting and incrementality estimation.\n"
            "Leverage ML and LLMs to create programmatic content at scale and build reinforcement "
            "learning systems for fast feedback loops.\n"
            "Qualifications: 3+ years of industry experience using machine learning to solve "
            "real-world problems; experience with e-commerce business problems; experience with LTV "
            "modeling, NLP, LLMs, or causal ML; strong programming skills; ability to design and "
            "implement ML solutions without supervision."
        ),
        "company_details": (
            "Faire operates an online wholesale marketplace that helps independent retailers compete "
            "with large chains by connecting them with makers and brands, powered by ML-driven "
            "recommendations and growth tools."
        ),
        "url": "https://jobs-radar.com/job/senior-applied-ai-ml-scientist-retailer-growth-at-faire-928be2",
    },
    {
        "job_id": "J23",
        "title": "Senior Product Manager, AI (eCommerce)",
        "company": "Cymax Group Technologies",
        "industry_domain": "E-commerce / Logistics Technology",
        "location": "Vancouver, BC",
        "required_skills": "Product management, AI/ML fundamentals, NLP, recommender systems, forecasting, optimization, cross-functional leadership",
        "years_experience": "5+",
        "description": (
            "Define and execute Cymax Group's AI product strategy as the company's AI Product "
            "Leader.\n"
            "Identify high-impact AI opportunities across pricing, merchandising, logistics, "
            "personalization, supply chain, demand forecasting, content generation, and customer "
            "support.\n"
            "Translate business needs into scalable AI-powered solutions and lead cross-functional "
            "teams to bring those solutions into production.\n"
            "Prioritize initiatives based on ROI, feasibility, and scalability, owning the full product "
            "lifecycle from discovery through launch.\n"
            "Qualifications: 5+ years in Product Management with significant experience in AI/ML-"
            "driven products; proven track record launching and scaling AI products in production; "
            "understanding of ML fundamentals including supervised/unsupervised learning, NLP, "
            "recommender systems, and forecasting; experience in e-commerce, marketplaces, retail, or "
            "supply chain businesses preferred."
        ),
        "company_details": (
            "Cymax Group Technologies is a tech-enabled brand accelerator that helps brands and "
            "retailers compete in the digital marketplace through automation, AI, and optimized "
            "logistics in the home and lifestyle category."
        ),
        "url": "https://ca.jobrapido.com/jobpreview/4798518944786808832",
    },
]

FIELDNAMES = [
    "job_id",
    "title",
    "company",
    "industry_domain",
    "location",
    "required_skills",
    "years_experience",
    "description",
    "company_details",
    "url",
]


def main():
    out_path = os.path.join(os.path.dirname(__file__), "..", "data", "jobs.csv")
    out_path = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for job in JOBS:
            writer.writerow(job)
    print(f"Wrote {len(JOBS)} jobs to {out_path}")


if __name__ == "__main__":
    main()
