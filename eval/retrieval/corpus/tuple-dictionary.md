<!-- Slide number: 1 -->
# Tuple and Dictionary

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 2 -->
# Tuple

Section 1

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 3 -->
# Tuple

- Declare a tuple
  - A tuple is a sequence of immutable Python objects.
  - Different comma-separated values between square parentheses
  - Zero-based sequences
  - To declare a tuple with a single value, we must include a comma

- my_tuple = (1, "hello", 3.14)

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 4 -->
# Tuple

- Benefits
- Keeps data fixed, prevents unwanted changes
  - Faster access than list
  - Can be used as a key in a dictionary
  - Cannot add, delete, or modify after creation

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 5 -->
# Tuple

- Access values
  - Use the square brackets for slicing with a certain index or indices to retrieve value(s) of the tuple

- subjects = ('physics', 'chemistry', 'math');
- print(subjects[0])	# physics
- print(subjects[2])	# math
- print(subjects[-l])	# math
- print(subjects[0:2])# ['physics', 'chemistry’]
- print(subjects[0:3])# ['physics', 'chemistry', 'math’]
- print(subjects[:])	# ['physics', 'chemistry', 'math']

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 6 -->
# Tuple

- Update Values
  - Tuples are immutable so we cannot update or change values of elements

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 7 -->
# Tuple

- Append values
  - Appending tuple elements is impossible.
- Delete values
  - Removing tuple elements is impossible.

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 8 -->
# Tuple

Basic Tuple Operation

| Python Expression | Results | Description |
| --- | --- | --- |
| len((1, 2, 3)) | 3 | Length |
| (1, 2, 3) + (4, 5, 6) | (1, 2, 3, 4, 5, 6) | Concatenation |
| ('Hello', 'time') * 2 | ('Hello', 'time', 'Hello', 'time') | Repetition |
| 3 in (1, 2, 3) | True | Membership |
| for x in (1, 2, 3): print x, | 12 3 | Iteration |

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 9 -->
# Tuple

- Built-in List Functions & Methods
  - len(tuple) Gives the total length of the tuple.
  - max(tuple) Returns item from the tuple with max value.
  - min(tuple) Returns item from the tuple with min value.
  - tuple(seq) Converts a list into tuple.

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 10 -->
# Dictionary

Section 2

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 11 -->
# Dictionary

- Declare a dictionary
  - Key-value storage, separated values by commas between two curly braces
  - Each key is separated from its value by a colon (:)
  - Keys must be unique and immutable (strings, numbers or tuples)
  - Values can be any type

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 12 -->
# Dictionary

- Access values
  - Use the square brackets with the key to retrieve its value
  - Retrieving value of a non-existing key will lead to KeyError

- registration = {'Name': 'Python', 'Year': 2018, 'Class': 'AI'}
- print(registration ['Name'])    # Python
- print(registration ['Year'])    # 2018

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 13 -->
# Dictionary

- Update values
  - Could add new entries with new key-value pairs
  - Could modify existing items by assigning new values

- registration = {'Name': 'Python', 'Year': 2018, 'Class': 'AI'}
- registration['Name'] = 'Data'
- registration['Course'] = 'Machine Learning'
- print(registration['Name'])    # Data
- print(registration['Course'])  # Machine Learning

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 14 -->
# Dictionary

- Delete values
  - Use the del statement to remove items
  - Use the clear() method to all entries

- registration = {'Name': 'Python', 'Year': 2018, 'Class': 'AI'}
- registration ['Name']	# remove entry with key 'Name’
- registration.clear()	# remove all entries in registration
- del dict	# delete entire dictionary

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 15 -->
# Dictionary

- Properties of Dictionary Keys
  - No duplicate key
  - Keys must be immutable

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 16 -->
# Dictionary

- Built-in List Functions
- cmp(dict1, dict2) Compares elements of both diet.
- len(dict) Gives the number of items of the dictionary.

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 17 -->
# Dictionary

- Built-in List Methods
  - dict.clear() Removes all elements of dictionary diet
  - dict.copy() Returns a shallow copy of dictionary diet
  - dict.fromkeys() Create a new dictionary with keys from seq and values set to value
  - dict.get(key, default=None) Returns value or default if key not in dictionary
  - dict.has_key(key) Returns true if key in dictionary dict, false otherwise
  - dict.items() Returns a list of dict's (key, value) tuple pairs
  - dict.keys() Returns list of dictionary dict's keys
  - dict.update(dict2) Adds dictionary dict2's key-values pairs to dict
  - dict.values() Returns list of dictionary dict's values

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 18 -->
# Let practice!

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use
