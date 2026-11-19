<!-- Slide number: 1 -->
# Python Introduction

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 2 -->
# Agenda

- Python Basic
  - Basic syntax
  - Variable, Operators, Data Types
  - Conditional Statement
  - Loops
- Number
- String

![slide_2_img_0.png](slide_2_img_0.png)

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 3 -->
# Python Basic

Section 1

Python for Data Science 1

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 4 -->
# Basic Syntax

- Line and Indentation
  - No braces for blocks of code
  - Line indentation indicate blocks of code
  - Same number of spaces for each line in a block of code
  - The number of spaces in the indentation is ﬂexible

- if True:
- print("True")
- else:
- print("False")

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 5 -->
# Basic Syntax

- Identiﬁers
  - Starts with a letter a to z or an underscore (_)
  - Could have any letters, underscores and digits (0 to 9)
  - Case sensitive programming language
  - Use snake_case convention

- user_day= 3
- _completed3 = True

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 6 -->
# Basic Syntax

Reserved Words

| and | exec | not |
| --- | --- | --- |
| assert | finally | or |
| break | for | pass |
| class | from | print |
| continue | global | raise |
| def | if | return |
| del | import | try |
| elif | in | while |
| else | is | with |
| except | lambda | yield |

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 7 -->
# Basic Syntax

- Quotations
  - Single ('), double (") and triple (''' or """) quotes to denote string literals
  - The triple quotes for multiple line strings.

- language = 'Python'
- class_name = "Machine Learning"
- paragraph = """The training duration is more than 10 weeks. 	It will prepare all basic knowledge."""

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 8 -->
# Basic Syntax

- Comments
  - A hash sign (#) starts a comment

- # The first program
- print("Hello, Python!") # The first statement

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 9 -->
# Variables

- Declaration and Assignment
  - Variables are reserved memory locations to store values.
  - Python variables do not need explicit declaration to reserve memory space.
  - The declaration is automatically when you assign a value to a variable by using the equal sign (=).

- counter	= 100   		# An integer assignment
- miles	= 1125.0   	# A floating point
- name	= "Hans"    	# A string

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 10 -->
# Variables

- Declaration and Assignment
  - Could assign a single value to several variables simultaneously
  - Could assign multiple objects to multiple variables.

- i = j = k = 1
- age, registered, name = 1, False, "Tony"

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 11 -->
# Variables

- Standard Data Types
  - Boolean, Numbers, String
  - String
  - List, Set
  - Tuple, Dictionary
- To get type: type()

- year = 2018
- name= "Tony Stark"
- language_list = ['Java', 'Python']
- package_set = {'Numpy', 'Pandas', 'Matplotlib'}
- week_days = ('Monday', 'Tuesday')
- tiny_dict = {'name': 'AI', 'code':2018, 'dept': 'FA'}

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 12 -->
# Variables

- Data Type Convention
  - int(x [,base]): Converts x to an integer. Base speciﬁes the base if x is a string.
  - long(x [,base]): Converts x to a long integer. Base speciﬁes the base if x is a string.
  - ﬂoat(x): Converts x to a ﬂoating-point number.
  - complex(real [,imag]): Creates a complex number.
  - str(x): Converts object x to a string representation.
  - tuple(s): Converts s to a tuple.
  - list(s): Converts s to a list.
  - set(s): Converts s to a set.
  - dict(d): Creates a dictionary. d must be a sequence of (key,value) tuples.

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 13 -->
# Operators

Arithmetic Operators

| Operator | Example |  |  |  |  |
| --- | --- | --- | --- | --- | --- |
| +	Addition | 10	+	20	=	30 |  |  |  |  |
| -	Subtraction | 10	–	20	=	-10 |  |  |  |  |
| *	Multiplication | 10	*	20	=	200 |  |  |  |  |
| /	Division | 20	/	10	=	2 |  |  |  |  |
| %	Modulus | 20	%	10	=	0 |  |  |  |  |
| **	Exponent | 10**20	=10	to	the	power	20 |  |  |  |  |
| //	Floor	Division | 9//2	= | 4, | 9.0//2.0	=	4.0, | -11//3	=	-4, | -11.0//3	=	-4.0 |

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 14 -->
# Operators

Comparison (Relational) Operators

| Operator | Example |
| --- | --- |
| == | (10	==	20)	is	not	true. |
| != | (10	!=	20)	is	true. |
| <> | (10	<>	20)	is	true.	(similar	to	!=	operator.) |
| > | (10	>	20)	is	not	true. |
| < | (10	<	20)	is	true. |
| >= | (10	>=	20)	is	not	true. |
| <= | (10	<=	20)	is	true. |

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 15 -->
# Operators

Assignment Operators

| Operator | Example |
| --- | --- |
| = | c	=	a	+	b |
| += | c	+=	a	is	equivalent	to	c	=	c	+	a |
| -= | c	-=	a	is	equivalent	to	c	=	c	-	a |
| *= | c	*=	a	is	equivalent	to	c	=	c	*	a |
| /= | c	/=	a	is	equivalent	to	c	=	c	/	a |
| %= | c	%=	a	is	equivalent	to	c	=	c	%	a |
| **= | c	**=	a	is	equivalent	to	c	=	c	**	a |
| //= | c	//=	a	is	equivalent	to	c	=	c	//	a |

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 16 -->
# Operators

Logical Operators

| Operator | Example |
| --- | --- |
| and	Logical	AND | (a	and	b)	is	true	if	both	a	and	b	are	true Other	cases	are	false |
| or	Logical	OR | (a	or	b)	is	false	if	both	a	and	b	are	false Other	cases	are	true |
| not	Logical	NOT | not(a)	is	false	if	a	is	true not(a)	is	true	if	a	is	false |

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 17 -->
# Operators

Membership Operators

| Operator | Example |
| --- | --- |
| in | x	in	y:	true	if	x	is	a	member	of	sequence	y. |
| not	in | x	not	in	y:	true	if	x	is	not	a	member	of	sequence	y. |

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 18 -->
# Operators

Identity Operators

| Operator | Example |
| --- | --- |
| is | x	is	y:	true	if	id(x)	equals	id(y). |
| is	not | x	is	not	y:	true	if	id(x)	is	not	equal	to	id(y). |

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 19 -->
# Decision Making

- if statements
- if expression:
- statement(s)

- year = 2018
- if year == 2018:
- print("Start the AI Fresher")

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 20 -->
# Decision Making

- if…elif…else
- if expression1:
- statement(s)
- elif expression2:
- statement(s)
- else:
- statement(s)

- year = 2018
- if year == 2018:
- print("Started the AI Fresher")
- elif year == 2017:
- print("Founded Fresher Academy")
- else:
- print("NA")

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 21 -->
# Loops

- for
- for iterating_var in sequence:
- statements(s)

- for letter in 'Python':
- print('Current Letter:', letter)

- fruits = ['banana', 'apple', 'mango']
- for index in range(len(fruits)):
- print('Current fruit:', fruits[index])

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 22 -->
# Loops

- while
- while expression:
- statement(s)

- count = 0
- while (count < 9):
- print('The count is:', count)
- count = count + 1

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 23 -->
# Loops

- break statement
  - The break statement terminates the current loop

- for letter in 'Python':
- if letter == 'h':
- break
- print('Current Letter:', letter)

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 24 -->
# Loops

- continue statement
  - The continue statement stops the current loop and starts next loops.

- for letter in 'Python':
- if letter == 'h':
- continue
- print('Current Letter:', letter)

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 25 -->
# Numbers

Section 4

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 26 -->
# Numbers

- Numerical types
  - int (signed integers)
  - long (long integers)
  - ﬂoat (ﬂoating point real values)
  - complex (complex numbers with the form a + bJ)

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 27 -->
# Numbers

- Number Type Conversion
  - int(x) to convert x to a plain integer.
  - long(x) to convert x to a long integer.
  - ﬂoat(x) to convert x to a ﬂoa@ng-point number.
  - complex(x) to convert x to a complex number with real part x and imaginary part zero.
  - complex(x, y) to convert x and y to a complex number with real part x and imaginary part y. x and y are numeric expressions.

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 28 -->
# Numbers

- Mathematical Functions
  - abs(x): The absolute value of x
  - ceil(x): The ceiling of x
  - exp(x): The exponential of x
  - ﬂoor(x): The ﬂoor of x (the largest integer not greater than x)
  - log(x): The natural logarithm of x, for x> 0
  - log10(x): The base-10 logarithm of x for x> 0.
  - max(x1, x2,...): The largest of its arguments
  - min(x1, x2,...): The smallest of its arguments
  - pow(x, y): The value of x**y.
  - round(x [,n]): x rounded to n digits from the decimal point.
  - sqrt(x): The square root of x for x > 0

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 29 -->
# Numbers

- Random numbers
  - choice(seq) A random item from a list, tuple, or string.
  - randrange ([start,] stop [,step]) A randomly selected element from range(start, stop, step)
  - random() A random ﬂoat r, such that 0 is less than or equal to r and r is less than 1
  - seed([x]) Sets the integer starting value used in generate random numbers.
  - shuﬄe(lst) Randomizes the items of a list in place.
  - uniform(x, y) A random ﬂoat r, such that x is less than or equal to r and r is less than y

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 30 -->
# Strings

Section 5

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 31 -->
# Strings

- Quotes
  - String is the most popular data type in Python.
  - Single quotes are the same as double quotes.

- language = 'Python'
- schoolName = "Fresher Academy"
- paragraph = """The training duration is more than 10 weeks. 	It will prepare all basic knowledge."""

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 32 -->
# Strings

Escape Characters

| Backslash notation | Description |
| --- | --- |
| \b | Backspace |
| \e | Escape |
| \n | Newline |
| \r | Carriage	return |
| \s | Space |
| \t | Tab |

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 33 -->
# Strings

String Special Operators

- a = "Hello"
- b = "Python"

| Operator | Example |
| --- | --- |
| + | a	+	b	will	give	HelloPython |
| * | a*2	will	give	-HelloHello |
| [] | a[1]	will	give	e |
| [	:	] | a[1:4]	will	give	ell |
| in | H	in	a	will	give	1 |
| not	in | M	not	in	a	will	give	1 |

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 34 -->
# Strings

String Formatting Operator (%)

| Format Symbol | Conversion |
| --- | --- |
| %c | character |
| %s | string	conversion	via	str()	prior	to	formatting |
| %i | signed	decimal	integer |
| %d | signed	decimal	integer |
| %u | unsigned	decimal	integer |
| %o | octal	integer |
| %x | hexadecimal	integer	(lowercase	letters) |
| %X | hexadecimal	integer	(UPPERcase	letters) |
| %e | exponential	notation	(with	lowercase	'e') |
| %E | exponential	notation	(with	UPPERcase	'E') |
| %f | floating	point	real	number |
| %g | the	shorter	of	%f	and	%e |
| %G | the	shorter	of	%f	and	%E |

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 35 -->
# Strings

Built-in String Method

- capitalize()
- find(str, beg=0 end=len(string))
- index(str, beg=0, end=len(string))
- isnumeric()
- join(seq)
- len(string)
- lower()
- max(str)
- min(str)

- replace(old,new [, max])
- rfind( str,beg = 0,end = len (string))
- rindex( str,beg = 0,end = len (string))
- split (str='',num = string.count (str))
- startswith (str,beg = 0,end = len (string))
- title()
- upper()

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use

<!-- page break -->

<!-- Slide number: 36 -->
# Let practice!

09e-BM/DT/FSOFT - @FPT SOFTWARE - FPT Software Academy - Internal Use
