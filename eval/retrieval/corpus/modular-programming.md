<!-- Slide number: 1 -->
# Modular Programming

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 2 -->
# Functions

Section 1

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 3 -->
# Function

- Define functions
- def function_name(parameters):
- "function_doc"
- function_statements
- return [expression]

- def sayHello(name):
- "To say hello to a name as a passed string"
- print("Hello " + name)
- return
- def add(a, b):
- "To sum of absolute values of both numbers"
- return abs(a) + abs(b)

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 4 -->
# Function

- Call functions
  - Call a function by using its name and necessary parameters

- sayHello("Python")	# Hello Python
- add(-3,4)	# 7

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 5 -->
# Function

- Pass by reference
- All parameters (arguments) in the Python language are passed by reference

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 6 -->
# Function

- Function arguments
  - Keyword arguments: the caller identifies the arguments by the parameter name.
  - Default arguments: Default values are used when parameter values are not provided
  - Variable-length arguments: An asterisk (*) is placed before a variable name holding values of all non-keyword variable arguments.

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 7 -->
# Function

- Return statements
  - Return a specific value
  - A return statement with no arguments ~ return None.

- def double(a, repeat):
- "To repeat input"
- a *= repeat
- return True
- scores = [1, 2, 3]
- double(scores, 2) # True
- print(scores)     # [1, 2, 3, 1, 2, 3]

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 8 -->
# Function

- Anonymous functions
  - Use the lambda keyword instead of the def keyword
  - Can take any number of arguments
  - Return only one value in the form of an expression.
  - Cannot be a direct call to print because lambda requires an expression
  - Can access only variables in the parameter list and the global namespace.

- sum = lambda x, y: x + y;
- print(sum(3, 4))    # 7
- print(sum(-3, 4))   # 1

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 9 -->
# Modules

Section 2

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 10 -->
# Modules

- What are Modules?
  - Modules are files containing Python definitions and statements (ex. name.py)
  - A module’s definitions can be imported into other modules by using “import name”
  - The module’s name is available as a global variable value
  - To access a module’s functions, type “name.function()”

<!-- page break -->

<!-- Slide number: 11 -->
# Modules

- The import statement
  - Use an import statement to import/add any Python source file as a module
  - A module is loaded only once when it is imported several times

- # Import module training
- import training
- # Can call defined function startClass in training
- training.startClass("AI")

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 12 -->
# Modules

- The from...import statement
  - Use from...import to import specific attributes from a module

- # Import module training
- from training import start.Class
- # Can call defined function startClass in training
- startClass("AI")

- # Import all functions in module training
- from training import *

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 13 -->
# File I/O

Section 3

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 14 -->
# File I/O

- The input statement
  - To read one line from standard input and returns it as a string

- name = input("Enter your name: ");
- print("Hi, ", name)

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 15 -->
# File I/O

- The open statement
  - fileObject = open(file_name[,access_mode][,buffering])

- # Open a file
- letter = open("letter.txt", "w")

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 16 -->
# File I/O

- The access modes to open files
  - r Opens a file for reading only.
  - rb Opens a file for reading only in binary format.
  - r+ Opens a file for both reading and writing.
  - rb+ Opens a file for both reading and writing in binary format.
  - w Opens a file for writing only.
  - wb Opens a file for writing only in binary format.
  - w+ Opens a file for both writing and reading.
  - wb+ Opens a file for both writing and reading in binary format.
  - a Opens a file for appending.
  - ab Opens a file for appending in binary format.
  - a+ Opens a file for both appending and reading.
  - ab+ Opens a file for both appending and reading in binary format.

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 17 -->
# File I/O

- The access modes to open files
  - r, rb, r+, rb+: The file pointer is placed at the beginning of the file.
  - w, wb, w+, wb+ Overwrite a file if the file exists. If the file does not exist, creates a new file for writing.
  - a, ab, a+, ab+ The file pointer is placed at the end of the file if the file exists. . If the file does not exist, creates a new file for writing.

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 18 -->
# File I/O

- The file Objects Attributes
  - file.closed Returns true if file is closed, false otherwise.
  - file.mode Returns access mode with which file was opened.
  - file.name Returns name of the file.
  - file.softspace Returns false if space explicitly required with print, true otherwise.

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 19 -->
# File I/O

- The close() method
  - fileObject.close();

- # Close opened file
- letter.close()

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 20 -->
# File I/O

- Write files
  - fileObject.write(contents);

- # Open a file
- letter = open("letter.txt", "w")
- letter.write("Python is a great language.\nWelcome!!\n");
- # Close opened file
- letter.close()

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 21 -->
# File I/O

- Read files
  - fileObject.read();

- # Open a file
- letter = open("letter.txt", "w")
- message = letter.read();
- # Close opened file
- letter.close()

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 22 -->
# File I/O

- The os Module
  - os.rename(current_file_name, new_file_name)
  - os.remove(file_name)
  - os.mkdir("newdir"): to create directories in the current directory
  - os.chdir("newdir"): to change the current directory
  - os.getcwd(): to display the current working directory
  - os.rmdir('dirname'): to delete the directory

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 23 -->
# File I/O

- Rename files

- import os
- # Rename a file from letter.txt to message.txt
- os.rename("letter.txt", "message.txt")

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 24 -->
# Exceptions

Section 4

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 25 -->
# Try…except…finally

- Exceptions versus Syntax Errors
- Raising an Exception
- The AssertionError Exception
- Handling Exceptions
- The else Clause

![slide_25_img_0.png](slide_25_img_0.png)

<!-- page break -->

<!-- Slide number: 26 -->
# Try…except…finally

- Exceptions versus Syntax Errors
  - Syntax errors occur when the parser detects an incorrect statement.

![slide_26_img_0.png](slide_26_img_0.png)

<!-- page break -->

<!-- Slide number: 27 -->
# Try…except…finally

- Raising an Exception
  - We can use raise to throw an exception if a condition occurs.

- x = 10
- if x > 5:
- raise Exception('x should not exceed 5. The value of x was: {}'.format(x))

<!-- page break -->

<!-- Slide number: 28 -->
# Try…except…finally

- The AssertionError Exception
  - We assert that a certain condition is met. If this condition turns out to be True, then that is excellent! The program can continue. If the condition turns out to be False, you can have the program throw an AssertionError exception.

- import sys
- assert ('linux' in sys.platform), "This code runs on Linux only."

<!-- page break -->

<!-- Slide number: 29 -->
# Try…except…finally

- The try block lets you test a block of code for errors.
- The except block lets you handle the error.
- The finally block lets you execute code, regardless of the result of the try- and except blocks.

<!-- page break -->

<!-- Slide number: 30 -->
# Try…except…finally

- The try and except Block
  - The try and except block in Python is used to catch and handle exceptions.

![slide_30_img_0.png](slide_30_img_0.png)

<!-- page break -->

<!-- Slide number: 31 -->
# Try…except…finally

The try and except Block

![slide_31_img_0.png](slide_31_img_0.png)

<!-- page break -->

<!-- Slide number: 32 -->
# Try…except…finally

The else Clause

![slide_32_img_0.png](slide_32_img_0.png)

<!-- page break -->

<!-- Slide number: 33 -->
# Try…except…finally

The else Clause

- try:
- linux_interaction('linux')
- except AssertionError as error:
- print(error)
- else:
- print('Executing the else clause.')

<!-- page break -->

<!-- Slide number: 34 -->
# Try…except…finally

Cleaning Up After Using finally

![slide_34_img_0.png](slide_34_img_0.png)

<!-- page break -->

<!-- Slide number: 35 -->
# Try…except…finally

Cleaning Up After Using finally

- try:
- linux_interaction('windows')
- except AssertionError as error:
- print(error)
- else:
- try:
- with open('file.log') as file:
- read_data = file.read()
- except FileNotFoundError as fnf_error:
- print(fnf_error)
- finally:
- print('Cleaning up, irrespective of any exceptions.')

<!-- page break -->

<!-- Slide number: 36 -->
# Let practice!

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use
