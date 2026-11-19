<!-- Slide number: 1 -->
# Python Collection data types

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 2 -->
# List

Section 1

Python for Data Science 1

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 3 -->
# List

- The important characteristics
  - Lists are ordered.
  - Lists can contain any arbitrary objects.
  - List elements can be accessed by index.
  - Lists can be nested to arbitrary depth.
  - Lists are mutable.
  - Lists are dynamic.

<!-- page break -->

<!-- Slide number: 4 -->
# List

Declare a list

- subjects = ['physics', 'chemistry', 'math']
- years = [2018, 2019, 2020, 2021, 2022]
- chars = ["a", "b", "c", "d"]

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 5 -->
# List

- Lists are ordered
  - A list is not merely a collection of objects.
  - It is an ordered collection of objects.
  - The order in which you specify the elements when you define a list is an innate characteristic of that list and is maintained for that list’s lifetime.

- a = ['a', 'b', 'c', 'd']
- b = ['b', 'a', 'd', 'c']
- a == b

<!-- page break -->

<!-- Slide number: 6 -->
# List

- Lists Can Contain Arbitrary Objects
  - A list can contain any assortment of objects

a = [21.42, 'foobar', 3, 4, 'bark', False, 3.14159]

<!-- page break -->

<!-- Slide number: 7 -->
# List

List Elements Can Be Accessed by Index

- a = ['foo', 'bar', 'baz', 'qux', 'quux', 'corge']
- print(a[0])
- print(a[-1])

<!-- page break -->

<!-- Slide number: 8 -->
# List

- List Elements Can Be Accessed by Index
  - Slicing also works

- a = ['foo', 'bar', 'baz', 'qux', 'quux', 'corge']
- print(a[0:2])
- print(a[-3:-1])

<!-- page break -->

<!-- Slide number: 9 -->
# List

- List Elements Can Be Accessed by Index
  - Other features of string slicing work analogously for list slicing as well

- print(a[:4], a[0:4])
- print(a[2:], a[2:len(a)])
- a[:4] + a[4:]
- a[:4] + a[4:] == a

<!-- page break -->

<!-- Slide number: 10 -->
# List

- Lists Can Be Nested
  - A list can contain sublists

![slide_10_img_0.png](slide_10_img_0.png)

<!-- page break -->

<!-- Slide number: 11 -->
# List

- Lists Are Mutable
  - Modifying a Single List Value
  - Modifying Multiple List Values

- a = ['foo', 'bar', 'baz', 'qux', 'quux', 'corge']
- a[2] = 'x'
- a[-2] = 10

- a = ['foo', 'bar', 'baz', 'qux', 'quux', 'corge']
- print(a[1:4])
- a[1:4] = [0.5, 0.1, 55, 33, 231, 1213]
- print(a)

<!-- page break -->

<!-- Slide number: 12 -->
# List

Basic List Operation

| Python Expression | Results | Description |
| --- | --- | --- |
| len([1, 2, 3]) | 3 | Length |
| [1, 2, 3] + [4, 5, 6] | [1, 2, 3, 4, 5, 6] | Concatenation |
| ['Hi!'] * 4 | ['Hi!', 'Hi!', 'Hi!', 'Hi!'] | Repetition |
| 3 in [1, 2, 3] | TRUE | Membership |
| for x in [1, 2, 3]: print x, | 123 | Iteration |

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 13 -->
# List

- Methods That Modify a List
  - a.append(<obj>)
  - a.extend(<iterable>)
  - a.insert(<index>, <obj>)
  - a.remove(<obj>)
  - a.pop(index=-1)

<!-- page break -->

<!-- Slide number: 14 -->
# Set

Section 2

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 15 -->
# Set

- An unordered collection of elements
- Automatically removes duplicates
- Does not allow mutable elements inside (set, list, ...)
- Fast for existence checking

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 16 -->
# Set

- Create a set:
- my_set = {1, 2, 3, 3, 4}
- print(my_set) # {1, 2, 3, 4}

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 17 -->
# Set

- Built-in Set Methods
  - Add Items
  - Update Items

- thisset = {"banana", "apple", "cherry", 'kiwi', 'banana', 'apple'}
- thisset.add("orange")
- print(thisset)

- thisset = {"banana", "apple", "cherry", 'kiwi', 'banana', 'apple'}
- thisset.update(["orange", "mango", "grapes", "kiwi"])print(thisset)

<!-- page break -->

<!-- Slide number: 18 -->
# Set

- Built-in Set Methods
  - Remove Item with .remove()
  - Update Items with .discard()

- this_set = {"banana", "apple", "cherry", 'kiwi', 'banana', 'apple'}
- thisset.remove("banana")
- print(this_set)

this_set = {"banana", "apple", "cherry", 'kiwi', 'banana', 'apple'}this_set.discard("banana")print(this_set)

### Notes:
Note: If the item to remove does not exist, discard() will NOT raise an error.

<!-- page break -->

<!-- Slide number: 19 -->
# Benefits

- Easily remove duplicates
- Very fast element lookup (O(1))
- Supports powerful set operations
- Cannot access by index, no stable order

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 20 -->
# Set operations

- Create set: `{}` or `set()`
- Add element: `add()`
- Remove element: `remove()`
- Check element: `in`
- Union: `union()` or `|`
- Intersection: `intersection()` or `&`
- Difference: `difference()` or `-`
- Symmetric difference: `symmetric_difference()` or `^`

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 21 -->
# Set vs List

| Feature | List | Set |
| --- | --- | --- |
| Ordered | Yes | No |
| Duplicates | Yes | No |
| Search speed | Slower | Very fast |
| Index access | Yes | No |
| Set operations | No | Yes |

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 22 -->
# Tuple

Section 3

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 23 -->
# Tuple

- Declare a tuple
  - A tuple is a sequence of immutable Python objects.
  - Different comma-separated values between square parentheses
  - Zero-based sequences
  - To declare a tuple with a single value, we must include a comma

- my_tuple = (1, "hello", 3.14)

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 24 -->
# Tuple

- Benefits
- Keeps data fixed, prevents unwanted changes
  - Faster access than list
  - Can be used as a key in a dictionary
  - Cannot add, delete, or modify after creation

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 25 -->
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

<!-- Slide number: 26 -->
# Tuple

- Update Values
  - Tuples are immutable so we cannot update or change values of elements
- Append values
  - Appending tuple elements is impossible.
- Delete values
  - Removing tuple elements is impossible.

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 27 -->
# Dictionary

Section 4

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 28 -->
# Dictionary

- Dictionaries and lists share the following characteristics
  - Both are mutable.
  - Both are dynamic. They can grow and shrink as needed.
  - Both can be nested. A list can contain another list. A dictionary can contain another dictionary. A dictionary can also contain a list, and vice versa.

<!-- page break -->

<!-- Slide number: 29 -->
# Dictionary

- Dictionaries differ from lists primarily in how elements are accessed:
  - List elements are accessed by their position in the list, via indexing.
  - Dictionary elements are accessed via keys.

<!-- page break -->

<!-- Slide number: 30 -->
# Dictionary

- Declare a dictionary
  - Key-value storage, separated values by commas between two curly braces
  - Each key is separated from its value by a colon (:)
  - Keys must be unique and immutable (strings, numbers or tuples)
  - Values can be any type

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 31 -->
# Dictionary

- Access values
  - Use the square brackets with the key to retrieve its value
  - Retrieving value of a non-existing key will lead to KeyError

- registration = {'Name': 'Python', 'Year': 2018, 'Class': 'AI'}
- print(registration ['Name'])    # Python
- print(registration ['Year'])    # 2018

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 32 -->
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

<!-- Slide number: 33 -->
# Dictionary

- Delete values
  - Use the del statement to remove items
  - Use the clear() method to all entries

- registration = {'Name': 'Python', 'Year': 2018, 'Class': 'AI'}
- del registration['Name’]	# remove entry with key 'Name’
- registration.clear()	   # remove all entries in registration
- del registration 	   # delete entire dictionary

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 34 -->
# Dictionary

- Properties of Dictionary Keys
  - No duplicate key
  - Keys must be immutable

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 35 -->
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

<!-- Slide number: 36 -->
# Dictionary

- Check key before accessing or saving value
- if key in my_dict:
- value = my_dict[key]
- else:
- my_dict[key] = default_value

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 37 -->
# Dictionary

- Use .get(key, default) instead of direct access
  - Avoids KeyError
  - Provides fallback value
- >>> value = my_dict.get("age", 0)

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 38 -->
# Dictionary

- Use .setdefault() to initialize and return value
  - If key exists, return its value
  - If not, set it to default and return that
- >>> value = my_dict.setdefault("age", 0)

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 39 -->
# Dictionary

- Use collections.defaultdict for auto-initialization
  - Great for counters, grouping, and nested dicts
- from collections import defaultdict
- freq = defaultdict(int)
- for char in "banana":
- freq[char] += 1

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 40 -->
# Let practice!

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use
