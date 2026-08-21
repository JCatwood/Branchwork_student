# Branchwork

Branchwork is a private, GitHub-based application for individualized homework,
exams, feedback, and solutions. It is a database-free Django application that
runs only on the student's computer.

## Preparation

- install `git` if you don't have it on your laptop yet; see [here](https://git-scm.com/install) for reference
- install `python` if you don't have it on your laptop yet

## Create and clone your private repository

Use web browser:

1. Sign in to GitHub.
2. Select **Use this template** on the webpage of this app template repository.
3. Create a new **private** repository under your own GitHub account and name it `3349_2026F_<your name>`.
4. Go to your private repository, select the `student.yaml` file, click `Edit this file`, change `1234567` in the `student_id` field to your actual student ID and commit changes.
5. Add the instructor (ID: JCatwood) and TA (TBD) as collaborators.

On your laptop:
1. Choose/create a local directory for this homework app
2. Clone **your private repository** into that directory. You may need to authenticate to clone. For example, in the terminal, run
```bash
cd <some directory>
git clone <https://github.com/STUDENT_ACCOUNT/REPOSITORY_NAME.git>
cd <REPOSITORY_NAME>
```


## Configure git

You need to configure `git` before working on the homeworks. After verifying that `git` is available in your terminal, run
```bash
git config user.name "<Student Name>"
git config user.email "<student-email@example.com>"
```
Make sure that the email you use is the same as that used for your Github account.

## Prepare Python

Go to your cloned repository. Ideally, create a python virtual environment so that dependencies are managed in the local directory but this is optional. An example on macOS or Linux systems, open a terminal, run the following commands:
```bash
cd <directory_to_your_private_repository>
python -m venv .venv
source .venv/bin/activate
```
Windows users please search online or discuss with TA for the corresponding commands.

Next, install dependent python modules. Here's an example using binary installations, for which dependencies are usually self-contained.
```bash
python -m pip install -r requirements.txt --only-binary :all:
```

## Run the app

Each time you are ready to work on your homework/exam. First, go to your cloned repository and activate the python virtual environment, if any.
An example on macOS or Linux systems, open a terminal, run the following commands:
```bash
cd <directory_to_your_private_repository>
source .venv/bin/activate
```

To start the app, simply run
```bash
python run.py
```
Open <http://127.0.0.1:8000/>. To stop the app, click `Ctrl+C` in the same terminal.

## Usage

- Each time you run the app, please first select **Get updates from instructor** on the homepage. This will download new homeworks and grading.
- You can click an active homework and start working on it.
- When you are done, click **Save answers** to save your answers locally on your laptop.
- When you are ready to submit your homework to the instructor, click **Submit to GitHub**. This will submit your homework to the GitHub server accessible by your instructor.
- After clicking **Submit to GitHub**, please confirm that Branchwork reports a successful GitHub push and commit ID.
- You may make modifications and submit again before the due date.

