<!-- Slide number: 1 -->
# Python String and Regex

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 2 -->
# Agenda

- String manipulation
- Regular Expressions (Regex)
- Apply Regex to process real-world text data

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 3 -->
# String manipulation

Section 1

Python for Data Science 1

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 4 -->
# Python string

- Sequence of characters: "", ''
- Can contain any characters (letters, numbers, special characters)
- Very common data type

- s1 = "Hello"
- s2 = 'World'
- s3 = """Multi-line string
- can go to new lines"""

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

![slide_4_img_0.png](slide_4_img_0.png)

<!-- page break -->

<!-- Slide number: 5 -->
# String Characteristics

- String is immutable (cannot be changed after creation)
- Can access each character by index

- s = "Python"
- print(s[0]) # P
- print(s[-1]) # n
- print(s[1:4]) # yth
- print(s[:3]) # Pyt
- print(s[3:]) # hon

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 6 -->
# String Length and Membership

- String is immutable (cannot be changed after creation)
- Can access each character by index

- s = "Python"
- print(len(s)) # 6
- print("th" in s) # True
- for c in "abc":
- print(c)

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 7 -->
# Common String Methods

- lower()
- upper()
- capitalize()
- strip(), lstrip(), rstrip()
- replace()
- split(), join()

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 8 -->
# Checking String Start/End

- Checking String Start/End
- s = "python.txt"
- print(s.startswith("py")) # True
- print(s.endswith(".txt")) # True
- Checking for Digits/Letters
- s = "123"
- print(s.isdigit()) # True
- print("abc".isalpha()) # True
- print("abc123".isalnum()) # True

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 9 -->
# String Formatting

- String Formatting (f-string)
- name = "Alice"
- age = 23
- print(f"{name} is {age} years old")
- String Formatting with format()
- s = "Hello, {}. You are {} years old."
- print(s.format("Bob", 30))

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 10 -->
# Regular Expression

Section 2

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 11 -->
# Regex

- A pattern language for searching, checking, and extracting complex strings
- The `re` library in Python provides strong support
- import re
- text = "Email: abc@gmail.com"
- pattern = r"\w+@\w+\.\w+"
- result = re.search(pattern, text)
- print(result.group())

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 12 -->
# Regex

- Remove special characters
- Normalize phone number, email formats
- Split words, sentences in text

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 13 -->
# Basic Regex Symbols

![slide_13_img_0.png](slide_13_img_0.png)

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 14 -->
# Regex Flags

| Short flag | Full flag | Meaning |
| --- | --- | --- |
| re.A | re.ASCII | Perform ASCII-only matching instead of full Unicode matching |
| re.I | re.IGNORECASE | Perform case-insensitive matching |
| re.M | re.MULTILINE | This flag is used with metacharacter ^ (caret) and $ (dollar).When this flag is specified, the metacharacter ^ matches the pattern at beginning of the string and each newline’s beginning (\n).And the metacharacter $ matches pattern at the end of the string and the end of each new line (\n) |
| re.S | re.DOTALL | Make the DOT (.) special character match any character at all, including a newline. Without this flag, DOT(.) will match anything except a newline |
| re.X | re.VERBOSE | Allow comment in the regex. This flag is useful to make regex more readable by allowing comments in the regex. |
| re.L | re.LOCALE | Perform case-insensitive matching dependent on the current locale. Use only with bytes patterns |
| re.I | re.IGNORECASE | Perform case-insensitive matching |

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 15 -->
# Slide 15

![slide_15_img_0.png](slide_15_img_0.png)

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 16 -->
# Regex functions

- import re
- emails = re.findall(r"\w+@\w+\.\w+", "a@b.com, c@d.com")
- print(emails)

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 17 -->
# Regex functions

- import re
- text = "abc123"
- print(re.sub(r"\d", "*", text)) # abc***

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 18 -->
# Regex functions

- import re
- print(re.match(r"\d+", "123abc")) # match
- print(re.match(r"\d+", "abc123")) # None

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 19 -->
# Regex functions

- import re
- text = "Name: Alice, Age: 23"
- pattern = r"Name: (\w+), Age: (\d+)"
- result = re.search(pattern, text)
- print(result.group(1)) # Alice
- print(result.group(2)) # 23

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 20 -->
# Example

- import re
- email = "abc@gmail.com"
- if re.match(r"^\w+@\w+\.\w+$", email):
- print("Valid email")
- else:
- print("Invalid email")

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 21 -->
# Example

- import re
- text = "Date: 25/06/2025"
- date = re.search(r"\d{2}/\d{2}/\d{4}", text)
- print(date.group())

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 22 -->
# Example

- import re
- text = "Contact: 0987-654-321 or 0912-345-678"
- phones = re.findall(r"\d{4}-\d{3}-\d{3}", text)
- print(phones)

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 23 -->
# Using convention

- Regex is case-sensitive
- Always test your regex with various cases
- You can use online tools to test regex

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 24 -->
# Let practice!

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use
